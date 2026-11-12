"""The workshop's stock in the admin area (``/api/v1/admin/inventory``)."""

from collections.abc import Sequence
from io import BytesIO
from typing import Annotated, Final
from unicodedata import normalize
from urllib.parse import quote
from uuid import UUID
from zipfile import ZIP_STORED, ZipFile

from fastapi import APIRouter, Query, Response, status
from starlette.concurrency import run_in_threadpool

from modellbahn.modules.inventory.api.deps import (
    AllocationServiceDep,
    AssemblyServiceDep,
    LabelServiceDep,
    LocationServiceDep,
    PartStoreServiceDep,
    ScanServiceDep,
    StockManager,
    StockWorker,
    UnitServiceDep,
)
from modellbahn.modules.inventory.api.errors import STAFF_ACCESS
from modellbahn.modules.inventory.api.schemas import (
    AssemblyIn,
    AssemblyOut,
    AssemblyPlanOut,
    LabelFormat,
    LabelsIn,
    LocationContentsOut,
    LocationCreateIn,
    LocationNodeOut,
    LocationOut,
    LocationPatchIn,
    LocationTreeOut,
    PartCountIn,
    PartDetailsOut,
    PartStockLineOut,
    PartStockOut,
    PickListOut,
    ReceiptOut,
    ReceivingOut,
    ScanIn,
    ScanOut,
    ScrapIn,
    StockLineOut,
    StockOut,
    UnitBatchOut,
    UnitDetailsOut,
    UnitListOut,
    UnitMoveIn,
    UnitMoveOut,
    UnitOut,
    UnitScrapOut,
    UnitsCreateIn,
    UnitsScrapIn,
    WriteOffIn,
)
from modellbahn.modules.inventory.application.labels import LabelRequest
from modellbahn.modules.inventory.application.scanning import ScanRequest
from modellbahn.modules.inventory.domain.model import UnitStatus
from modellbahn.modules.inventory.domain.parts import KITS_PER_ASSEMBLY_MAX
from modellbahn.platform.errors import problems
from modellbahn.platform.pdf_images import pdf_to_pngs

router = APIRouter(prefix="/admin/inventory", tags=["admin-inventory"])

_LOCATION_NOT_FOUND: Final = {404: ["location_not_found"]}
_UNIT_NOT_FOUND: Final = {404: ["unit_not_found"]}
_ORDER_NOT_FOUND: Final = {404: ["order_not_found"]}
_PART_NOT_FOUND: Final = {404: ["part_not_found"]}
_PDF: Final = "application/pdf"
_PNG: Final = "image/png"
_ZIP: Final = "application/zip"


# --- Locations ------------------------------------------------------------------------


@router.get(
    "/locations",
    operation_id="listLocations",
    summary="The location tree with unit counts",
    responses=problems(STAFF_ACCESS, unsafe=False, validated=False),
)
async def list_locations(_: StockWorker, service: LocationServiceDep) -> LocationTreeOut:
    return LocationTreeOut(items=[LocationNodeOut.from_node(node) for node in await service.tree()])


@router.post(
    "/locations",
    operation_id="createLocation",
    summary="Add a site, shelf, compartment, box or staging area",
    status_code=status.HTTP_201_CREATED,
    responses=problems({**STAFF_ACCESS, **_LOCATION_NOT_FOUND, 409: ["location_code_taken"]}),
)
async def create_location(
    body: LocationCreateIn, _: StockManager, service: LocationServiceDep
) -> LocationOut:
    location = await service.create(
        parent_code=body.parent_code or None,
        segment=body.segment,
        kind=body.kind,
        name=body.name,
    )
    return LocationOut.from_location(location)


@router.get(
    "/locations/{code}",
    operation_id="getLocation",
    summary="A location with its sub-locations and the units in it",
    responses=problems({**STAFF_ACCESS, **_LOCATION_NOT_FOUND}, unsafe=False),
)
async def get_location(
    code: str, _: StockWorker, service: LocationServiceDep
) -> LocationContentsOut:
    return LocationContentsOut.from_contents(await service.contents(code.upper()))


@router.patch(
    "/locations/{code}",
    operation_id="renameLocation",
    summary="Rename a location (its code stays: it is on the label)",
    responses=problems({**STAFF_ACCESS, **_LOCATION_NOT_FOUND}),
)
async def rename_location(
    code: str, body: LocationPatchIn, _: StockManager, service: LocationServiceDep
) -> LocationOut:
    return LocationOut.from_location(await service.rename(code.upper(), name=body.name))


@router.delete(
    "/locations/{code}",
    operation_id="deleteLocation",
    summary="Remove an empty location that never held goods",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=problems(
        {
            **STAFF_ACCESS,
            **_LOCATION_NOT_FOUND,
            409: ["location_not_empty", "location_in_use"],
        },
    ),
)
async def delete_location(code: str, _: StockManager, service: LocationServiceDep) -> Response:
    await service.remove(code.upper())
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- Units ----------------------------------------------------------------------------


@router.get(
    "/stock",
    operation_id="listStock",
    summary="Units per variant and state, with backorders",
    responses=problems(STAFF_ACCESS, unsafe=False, validated=False),
)
async def list_stock(_: StockWorker, service: UnitServiceDep) -> StockOut:
    return StockOut(items=[StockLineOut.from_line(line) for line in await service.stock()])


@router.get(
    "/units",
    operation_id="listUnits",
    summary="Pieces, oldest first: of one article, in some states, or both",
    description="`status` may repeat. Without filters every piece ever labelled is listed.",
    responses=problems(STAFF_ACCESS, unsafe=False),
)
async def list_units(
    _: StockWorker,
    service: UnitServiceDep,
    variant_id: Annotated[UUID | None, Query()] = None,
    status_filter: Annotated[list[UnitStatus] | None, Query(alias="status")] = None,
) -> UnitListOut:
    listed = await service.list_units(
        variant_id, statuses=frozenset(status_filter) if status_filter else None
    )
    return UnitListOut.from_list(listed)


@router.post(
    "/units",
    operation_id="labelUnits",
    summary="New units of a variant, ready for their labels (optionally put away at once)",
    status_code=status.HTTP_201_CREATED,
    responses=problems({**STAFF_ACCESS, 404: ["variant_not_found", "location_not_found"]}),
)
async def label_units(
    body: UnitsCreateIn, staff: StockManager, service: UnitServiceDep
) -> UnitBatchOut:
    views = await service.label_units(
        variant_id=body.variant_id,
        quantity=body.quantity,
        location_code=body.location_code or None,
        staff_id=staff.id,
    )
    return UnitBatchOut(items=[UnitOut.from_view(view) for view in views])


@router.post(
    "/units/moves",
    operation_id="moveUnits",
    summary="Put several units into one location in one go, all or none (without scanning)",
    description="Booked like the put-away scan. Units already there are left alone, so a "
    "repeated request is harmless; a picked, shipped, scrapped or unknown unit refuses the "
    "whole request and `detail` names them.",
    responses=problems({**STAFF_ACCESS, **_LOCATION_NOT_FOUND, 409: ["units_not_movable"]}),
)
async def move_units(body: UnitMoveIn, staff: StockWorker, service: UnitServiceDep) -> UnitMoveOut:
    move = await service.move_units(
        body.unit_ids, location_code=body.location_code, staff_id=staff.id
    )
    return UnitMoveOut.from_move(move)


@router.post(
    "/units/scraps",
    operation_id="scrapUnits",
    summary="Take several units out of stock in one go, with a reason, all or none",
    description="Booked like scrapping one unit. Units already out are left alone; a unit "
    "picked or shipped for an order, or an unknown one, refuses the whole request and "
    "`detail` names them.",
    responses=problems({**STAFF_ACCESS, 409: ["units_not_scrappable"]}),
)
async def scrap_units(
    body: UnitsScrapIn, staff: StockManager, service: UnitServiceDep
) -> UnitScrapOut:
    scrap = await service.scrap_units(
        body.unit_ids, reason=body.reason, note=body.note, staff_id=staff.id
    )
    return UnitScrapOut.from_scrap(scrap)


@router.get(
    "/units/{code}",
    operation_id="getUnit",
    summary="A unit with what it is, where it lies and its whole history",
    responses=problems({**STAFF_ACCESS, **_UNIT_NOT_FOUND}, unsafe=False),
)
async def get_unit(code: str, _: StockWorker, service: UnitServiceDep) -> UnitDetailsOut:
    return UnitDetailsOut.from_details(await service.details(code))


@router.post(
    "/units/{code}/scrap",
    operation_id="scrapUnit",
    summary="Take a broken or lost unit out of stock; its order gets another one",
    responses=problems({**STAFF_ACCESS, **_UNIT_NOT_FOUND, 409: ["invalid_unit_state"]}),
)
async def scrap_unit(
    code: str, body: ScrapIn, staff: StockManager, service: UnitServiceDep
) -> UnitOut:
    view = await service.scrap(code, note=body.note, reason=body.reason, staff_id=staff.id)
    return UnitOut.from_view(view)


# --- Parts ----------------------------------------------------------------------------


@router.get(
    "/parts",
    operation_id="listPartStock",
    summary="Printed parts in stock and in receiving, by part number",
    responses=problems(STAFF_ACCESS, unsafe=False, validated=False),
)
async def list_part_stock(_: StockWorker, service: PartStoreServiceDep) -> PartStockOut:
    return PartStockOut(
        items=[PartStockLineOut.from_line(line) for line in await service.overview()]
    )


@router.get(
    "/parts/{part_number}",
    operation_id="getPartStock",
    summary="A part with its boxes, what waits in receiving, and its journal",
    responses=problems({**STAFF_ACCESS, **_PART_NOT_FOUND}, unsafe=False),
)
async def get_part_stock(
    part_number: str, _: StockWorker, service: PartStoreServiceDep
) -> PartDetailsOut:
    return PartDetailsOut.from_details(await service.details(part_number))


@router.post(
    "/parts/{part_number}/count",
    operation_id="countParts",
    summary="Set a part's quantity in a location to what was counted there",
    responses=problems({**STAFF_ACCESS, 404: ["part_not_found", "location_not_found"]}),
)
async def count_parts(
    part_number: str, body: PartCountIn, staff: StockManager, service: PartStoreServiceDep
) -> PartDetailsOut:
    details = await service.count(
        part_number,
        location_code=body.location_code,
        quantity=body.quantity,
        note=body.note,
        staff_id=staff.id,
    )
    return PartDetailsOut.from_details(details)


@router.get(
    "/receiving",
    operation_id="listReceiving",
    summary="Good parts of finished plates that wait to be put into a box",
    responses=problems(STAFF_ACCESS, unsafe=False, validated=False),
)
async def list_receiving(_: StockWorker, service: PartStoreServiceDep) -> ReceivingOut:
    return ReceivingOut(items=[ReceiptOut.from_view(view) for view in await service.receiving()])


@router.post(
    "/receiving/{receipt_id}/write-off",
    operation_id="writeOffReceipt",
    summary="The rest of a receipt never reached a shelf: take it out of receiving",
    responses=problems(
        {**STAFF_ACCESS, 404: ["receipt_not_found"], 409: ["invalid_receipt_state"]}
    ),
)
async def write_off_receipt(
    receipt_id: UUID, body: WriteOffIn, staff: StockManager, service: PartStoreServiceDep
) -> ReceiptOut:
    return ReceiptOut.from_view(
        await service.write_off(receipt_id, note=body.note, staff_id=staff.id)
    )


# --- Assembly -------------------------------------------------------------------------


@router.get(
    "/assembly-plan",
    operation_id="planAssembly",
    summary="Which parts kits of a variant take, and from which boxes",
    responses=problems(
        {**STAFF_ACCESS, 404: ["variant_not_found"], 409: ["no_bill_of_materials"]},
        unsafe=False,
    ),
)
async def plan_assembly(
    variant_id: UUID,
    quantity: Annotated[int, Query(ge=1, le=KITS_PER_ASSEMBLY_MAX)],
    _: StockWorker,
    service: AssemblyServiceDep,
) -> AssemblyPlanOut:
    return AssemblyPlanOut.from_plan(await service.plan(variant_id, quantity))


@router.post(
    "/assemblies",
    operation_id="assemble",
    summary="Take the parts out of their boxes and label the new units",
    status_code=status.HTTP_201_CREATED,
    responses=problems(
        {
            **STAFF_ACCESS,
            404: ["variant_not_found", "location_not_found"],
            409: ["no_bill_of_materials", "parts_missing"],
        }
    ),
)
async def assemble(
    body: AssemblyIn, staff: StockManager, service: AssemblyServiceDep
) -> AssemblyOut:
    assembly = await service.assemble(
        body.variant_id,
        body.quantity,
        location_code=body.location_code or None,
        staff_id=staff.id,
    )
    return AssemblyOut.from_assembly(assembly)


# --- Scans ----------------------------------------------------------------------------


@router.post(
    "/scans",
    operation_id="recordScan",
    summary="The central scan command: put away, pick or look up; idempotent by scan id",
    responses=problems({**STAFF_ACCESS, 409: ["scan_id_reused"]}),
)
async def record_scan(body: ScanIn, staff: StockWorker, service: ScanServiceDep) -> ScanOut:
    answer = await service.scan(
        ScanRequest(
            scan_id=body.scan_id,
            raw=body.raw,
            mode=body.mode,
            source=body.source,
            context={str(key): value for key, value in body.context.items()},
        ),
        staff_id=staff.id,
    )
    return ScanOut.model_validate(answer)


@router.post(
    "/scans/{scan_id}/undo",
    operation_id="undoScan",
    summary="Book a scan backwards (within ten minutes, while its units have not moved on)",
    responses=problems(
        {
            **STAFF_ACCESS,
            404: ["scan_not_found"],
            409: [
                "scan_already_undone",
                "scan_too_old",
                "scan_nothing_booked",
                "scan_changed_since",
            ],
        },
    ),
)
async def undo_scan(scan_id: UUID, staff: StockWorker, service: ScanServiceDep) -> ScanOut:
    return ScanOut.model_validate(await service.undo(scan_id, staff_id=staff.id))


# --- Picking --------------------------------------------------------------------------


@router.get(
    "/orders/{order_id}/pick-list",
    operation_id="getPickList",
    summary="The order's pieces in walking order, with units and locations",
    responses=problems({**STAFF_ACCESS, **_ORDER_NOT_FOUND}, unsafe=False),
)
async def get_pick_list(
    order_id: UUID, _: StockWorker, service: AllocationServiceDep
) -> PickListOut:
    return PickListOut.from_pick_list(await service.pick_list(order_id))


@router.post(
    "/orders/{order_id}/allocation",
    operation_id="allocateOrder",
    summary="Allocate a paid order now (happens by itself when the payment comes in)",
    responses=problems({**STAFF_ACCESS, **_ORDER_NOT_FOUND, 409: ["order_not_allocatable"]}),
)
async def allocate_order(
    order_id: UUID, staff: StockManager, service: AllocationServiceDep
) -> PickListOut:
    return PickListOut.from_pick_list(await service.allocate_order(order_id, staff_id=staff.id))


# --- Labels ---------------------------------------------------------------------------


@router.post(
    "/labels",
    operation_id="printLabels",
    summary="Labels for units and locations as PDF, for A4 sheets or the Brother QL",
    description="With `format: png` (QL roll only) one picture per label at 300 dpi, for "
    "Brother's apps; a single label comes as PNG, several as a ZIP of PNGs.",
    response_class=Response,
    responses={
        200: {
            "description": "The labels as PDF, PNG or ZIP of PNGs.",
            "content": {
                _PDF: {"schema": {"type": "string", "format": "binary"}},
                _PNG: {"schema": {"type": "string", "format": "binary"}},
                _ZIP: {"schema": {"type": "string", "format": "binary"}},
            },
        },
        **problems(STAFF_ACCESS),
    },
)
async def print_labels(body: LabelsIn, _: StockWorker, service: LabelServiceDep) -> Response:
    printed = await service.render(
        LabelRequest(
            unit_codes=body.unit_codes,
            location_codes=body.location_codes,
            part_numbers=body.part_numbers,
            sheet=body.sheet,
            skip=body.skip,
        )
    )
    if body.format is LabelFormat.PDF:
        return _download(printed.pdf, _PDF, f"{printed.name}.pdf")
    pictures = await run_in_threadpool(pdf_to_pngs, printed.pdf)
    names = printed.names if len(printed.names) == len(pictures) else ()
    if len(pictures) == 1:
        return _download(pictures[0], _PNG, f"{names[0] if names else printed.name}.png")
    return _download(_zipped(pictures, names), _ZIP, f"{printed.name}.zip")


# Umlauts spelled out for the plain ASCII name that old clients read.
_ASCII_SPELLING: Final = str.maketrans(
    {"ä": "ae", "ö": "oe", "ü": "ue", "Ä": "Ae", "Ö": "Oe", "Ü": "Ue", "ß": "ss"}
)


def _download(content: bytes, media_type: str, filename: str) -> Response:
    """Named after the labels' model and variant: browsers take ``filename*`` (UTF-8,
    RFC 6266), older clients the ASCII spelling."""
    plain = normalize("NFKD", filename.translate(_ASCII_SPELLING))
    plain = plain.encode("ascii", "ignore").decode().replace('"', "")
    disposition = f"inline; filename=\"{plain}\"; filename*=UTF-8''{quote(filename)}"
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": disposition, "Cache-Control": "no-store"},
    )


def _zipped(pictures: list[bytes], names: Sequence[str]) -> bytes:
    """``01 IFA ADK 70 Autokran H0 Fertigmodell Gelb 7KQ2X9F4MZ.png`` … in print order."""
    buffer = BytesIO()
    with ZipFile(buffer, "w", ZIP_STORED) as archive:
        for number, picture in enumerate(pictures, start=1):
            name = names[number - 1] if names else "Etikett"
            archive.writestr(f"{number:02d} {name}.png", picture)
    return buffer.getvalue()
