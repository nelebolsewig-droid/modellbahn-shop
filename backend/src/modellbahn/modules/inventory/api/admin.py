"""The workshop's stock in the admin area (``/api/v1/admin/inventory``)."""

from typing import Final
from uuid import UUID

from fastapi import APIRouter, Response, status

from modellbahn.modules.inventory.api.deps import (
    AllocationServiceDep,
    LabelServiceDep,
    LocationServiceDep,
    ScanServiceDep,
    StockManager,
    StockWorker,
    UnitServiceDep,
)
from modellbahn.modules.inventory.api.errors import STAFF_ACCESS
from modellbahn.modules.inventory.api.schemas import (
    LabelsIn,
    LocationContentsOut,
    LocationCreateIn,
    LocationNodeOut,
    LocationOut,
    LocationPatchIn,
    LocationTreeOut,
    PickListOut,
    ScanIn,
    ScanOut,
    ScrapIn,
    StockLineOut,
    StockOut,
    UnitBatchOut,
    UnitDetailsOut,
    UnitOut,
    UnitsCreateIn,
)
from modellbahn.modules.inventory.application.labels import LabelRequest
from modellbahn.modules.inventory.application.scanning import ScanRequest
from modellbahn.platform.errors import problems

router = APIRouter(prefix="/admin/inventory", tags=["admin-inventory"])

_LOCATION_NOT_FOUND: Final = {404: ["location_not_found"]}
_UNIT_NOT_FOUND: Final = {404: ["unit_not_found"]}
_ORDER_NOT_FOUND: Final = {404: ["order_not_found"]}
_PDF: Final = "application/pdf"


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
    responses=problems({**STAFF_ACCESS, **_LOCATION_NOT_FOUND}, unsafe=False, validated=False),
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
        validated=False,
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


@router.get(
    "/units/{code}",
    operation_id="getUnit",
    summary="A unit with what it is, where it lies and its whole history",
    responses=problems({**STAFF_ACCESS, **_UNIT_NOT_FOUND}, unsafe=False, validated=False),
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
    return UnitOut.from_view(await service.scrap(code, note=body.note, staff_id=staff.id))


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
        validated=False,
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
    response_class=Response,
    responses={
        200: {
            "description": "The labels as PDF.",
            "content": {_PDF: {"schema": {"type": "string", "format": "binary"}}},
        },
        **problems(STAFF_ACCESS),
    },
)
async def print_labels(body: LabelsIn, _: StockWorker, service: LabelServiceDep) -> Response:
    pdf = await service.render(
        LabelRequest(
            unit_codes=body.unit_codes,
            location_codes=body.location_codes,
            sheet=body.sheet,
            skip=body.skip,
        )
    )
    return Response(
        content=pdf,
        media_type=_PDF,
        headers={
            "Content-Disposition": 'inline; filename="etiketten.pdf"',
            "Cache-Control": "no-store",
        },
    )
