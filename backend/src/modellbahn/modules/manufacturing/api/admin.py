"""The workshop's manufacturing in the admin area (``/api/v1/admin/manufacturing``)."""

from typing import Annotated, Final
from uuid import UUID

from fastapi import APIRouter, Query, Response, status

from modellbahn.modules.manufacturing.api.deps import (
    BomServiceDep,
    MaterialServiceDep,
    PartServiceDep,
    PrinterOperator,
    PrinterServiceDep,
    PrintJobServiceDep,
    ProductionPlanner,
)
from modellbahn.modules.manufacturing.api.errors import PRINTER_UNAVAILABLE, STAFF_ACCESS
from modellbahn.modules.manufacturing.api.schemas import (
    BomIn,
    BomOut,
    HallOut,
    MaterialCreateIn,
    MaterialIn,
    MaterialListOut,
    MaterialOut,
    PartCreateIn,
    PartIn,
    PartListOut,
    PartOut,
    PartRecordOut,
    PrinterCreateIn,
    PrinterIn,
    PrinterOut,
    PrinterRecordOut,
    PrinterStatusIn,
    PrintJobCompleteIn,
    PrintJobCreateIn,
    PrintJobFailIn,
    PrintJobListOut,
    PrintJobOut,
    PrintJobPlanIn,
    job_out,
)
from modellbahn.modules.manufacturing.domain.model import PrintJobStatus, Technology
from modellbahn.platform.errors import problems

router = APIRouter(prefix="/admin/manufacturing", tags=["admin-manufacturing"])

_PRINTER_NOT_FOUND: Final = {404: ["printer_not_found"]}
_MATERIAL_NOT_FOUND: Final = {404: ["material_not_found"]}
_PART_NOT_FOUND: Final = {404: ["part_not_found"]}
_JOB_NOT_FOUND: Final = {404: ["print_job_not_found"]}
_JOB_STATE: Final = ["invalid_print_job_state"]


# --- Printers -------------------------------------------------------------------------


@router.get(
    "/hall",
    operation_id="getPrinterHall",
    summary="Every printer with its state, its plate and its queue",
    responses=problems(STAFF_ACCESS, unsafe=False, validated=False),
)
async def printer_hall(_: PrinterOperator, service: PrinterServiceDep) -> HallOut:
    return HallOut.from_hall(await service.hall())


@router.get(
    "/printers/{printer_id}",
    operation_id="getPrinter",
    summary="A printer with its status reports and its latest plates",
    responses=problems({**STAFF_ACCESS, **_PRINTER_NOT_FOUND}, unsafe=False),
)
async def get_printer(
    printer_id: UUID, _: PrinterOperator, service: PrinterServiceDep
) -> PrinterRecordOut:
    return PrinterRecordOut.from_record(await service.record(printer_id))


@router.post(
    "/printers",
    status_code=status.HTTP_201_CREATED,
    operation_id="createPrinter",
    summary="Add a printer (in service)",
    responses=problems(STAFF_ACCESS),
)
async def create_printer(
    body: PrinterCreateIn, staff: ProductionPlanner, service: PrinterServiceDep
) -> PrinterOut:
    printer = await service.create(body.details(), technology=body.technology, staff_id=staff.id)
    return PrinterOut.from_printer(printer)


@router.put(
    "/printers/{printer_id}",
    operation_id="updatePrinter",
    summary="Change a printer (all of its details but its technology)",
    responses=problems({**STAFF_ACCESS, **_PRINTER_NOT_FOUND}),
)
async def update_printer(
    printer_id: UUID, body: PrinterIn, _: ProductionPlanner, service: PrinterServiceDep
) -> PrinterOut:
    return PrinterOut.from_printer(await service.change(printer_id, body.details()))


@router.delete(
    "/printers/{printer_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    operation_id="deletePrinter",
    summary="Remove a printer that never had a print job",
    responses=problems({**STAFF_ACCESS, **_PRINTER_NOT_FOUND, 409: ["printer_in_use"]}),
)
async def delete_printer(
    printer_id: UUID, _: ProductionPlanner, service: PrinterServiceDep
) -> Response:
    await service.delete(printer_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/printers/{printer_id}/status",
    operation_id="reportPrinterStatus",
    summary="Report the printer's state; a defect fails the plate printing on it",
    responses=problems(
        {**STAFF_ACCESS, **_PRINTER_NOT_FOUND, 409: ["printer_busy", "printer_has_queue"]}
    ),
)
async def report_printer_status(
    printer_id: UUID, body: PrinterStatusIn, staff: PrinterOperator, service: PrinterServiceDep
) -> PrinterOut:
    printer = await service.report(printer_id, body.status, note=body.note, staff_id=staff.id)
    return PrinterOut.from_printer(printer)


# --- Materials ------------------------------------------------------------------------


@router.get(
    "/materials",
    operation_id="listMaterials",
    summary="Every material, by technology and name",
    responses=problems(STAFF_ACCESS, unsafe=False, validated=False),
)
async def list_materials(_: PrinterOperator, service: MaterialServiceDep) -> MaterialListOut:
    return MaterialListOut(items=[MaterialOut.from_entry(entry) for entry in await service.all()])


@router.post(
    "/materials",
    status_code=status.HTTP_201_CREATED,
    operation_id="createMaterial",
    summary="Add a material",
    responses=problems(STAFF_ACCESS),
)
async def create_material(
    body: MaterialCreateIn, _: ProductionPlanner, service: MaterialServiceDep
) -> MaterialOut:
    entry = await service.create(name=body.name, technology=body.technology, notes=body.notes)
    return MaterialOut.from_entry(entry)


@router.put(
    "/materials/{material_id}",
    operation_id="updateMaterial",
    summary="Rename, describe or archive a material",
    responses=problems({**STAFF_ACCESS, **_MATERIAL_NOT_FOUND}),
)
async def update_material(
    material_id: UUID, body: MaterialIn, _: ProductionPlanner, service: MaterialServiceDep
) -> MaterialOut:
    entry = await service.change(material_id, name=body.name, notes=body.notes, active=body.active)
    return MaterialOut.from_entry(entry)


@router.delete(
    "/materials/{material_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    operation_id="deleteMaterial",
    summary="Remove a material no part is made of",
    responses=problems({**STAFF_ACCESS, **_MATERIAL_NOT_FOUND, 409: ["material_in_use"]}),
)
async def delete_material(
    material_id: UUID, _: ProductionPlanner, service: MaterialServiceDep
) -> Response:
    await service.delete(material_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- Parts ----------------------------------------------------------------------------


@router.get(
    "/parts",
    operation_id="listParts",
    summary="Parts by scale and part number",
    responses=problems(STAFF_ACCESS, unsafe=False),
)
async def list_parts(
    _: PrinterOperator,
    service: PartServiceDep,
    scale: Annotated[str | None, Query(max_length=4, description="Only this scale.")] = None,
    technology: Annotated[Technology | None, Query(description="Only this technology.")] = None,
    q: Annotated[
        str | None, Query(max_length=60, description="Part number or name contains this.")
    ] = None,
    archived: Annotated[bool, Query(description="Archived parts too.")] = False,
) -> PartListOut:
    entries = await service.search(
        scale_code=scale, technology=technology, query=q, include_archived=archived
    )
    return PartListOut(items=[PartOut.from_entry(entry) for entry in entries])


@router.get(
    "/parts/{part_id}",
    operation_id="getPart",
    summary="A part with the kits that need it and its latest plates",
    responses=problems({**STAFF_ACCESS, **_PART_NOT_FOUND}, unsafe=False),
)
async def get_part(part_id: UUID, _: PrinterOperator, service: PartServiceDep) -> PartRecordOut:
    return PartRecordOut.from_record(await service.record(part_id))


@router.post(
    "/parts",
    status_code=status.HTTP_201_CREATED,
    operation_id="createPart",
    summary="Add a part for one scale and technology",
    responses=problems(STAFF_ACCESS),
)
async def create_part(body: PartCreateIn, _: ProductionPlanner, service: PartServiceDep) -> PartOut:
    entry = await service.create(
        body.details(), scale_code=body.scale_code, technology=body.technology
    )
    return PartOut.from_entry(entry)


@router.put(
    "/parts/{part_id}",
    operation_id="updatePart",
    summary="Change a part (all of its details but scale and technology)",
    responses=problems({**STAFF_ACCESS, **_PART_NOT_FOUND}),
)
async def update_part(
    part_id: UUID, body: PartIn, _: ProductionPlanner, service: PartServiceDep
) -> PartOut:
    return PartOut.from_entry(await service.change(part_id, body.details(), active=body.active))


@router.delete(
    "/parts/{part_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    operation_id="deletePart",
    summary="Remove a part no kit needs and no plate carried",
    responses=problems({**STAFF_ACCESS, **_PART_NOT_FOUND, 409: ["part_in_use"]}),
)
async def delete_part(part_id: UUID, _: ProductionPlanner, service: PartServiceDep) -> Response:
    await service.delete(part_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- Bills of materials ---------------------------------------------------------------


@router.get(
    "/product-scales/{product_scale_id}/bom",
    operation_id="getBillOfMaterials",
    summary="The parts a product in one scale is made of",
    responses=problems({**STAFF_ACCESS, 404: ["product_scale_not_found"]}, unsafe=False),
)
async def get_bom(product_scale_id: UUID, _: PrinterOperator, service: BomServiceDep) -> BomOut:
    return BomOut.from_view(await service.get(product_scale_id))


@router.put(
    "/product-scales/{product_scale_id}/bom",
    operation_id="replaceBillOfMaterials",
    summary="Set the parts of a product in one scale; no lines removes them",
    responses=problems({**STAFF_ACCESS, 404: ["product_scale_not_found"]}),
)
async def replace_bom(
    product_scale_id: UUID, body: BomIn, staff: ProductionPlanner, service: BomServiceDep
) -> BomOut:
    view = await service.replace(
        product_scale_id,
        [(line.part_id, line.quantity) for line in body.lines],
        staff_id=staff.id,
    )
    return BomOut.from_view(view)


# --- Print jobs -----------------------------------------------------------------------


@router.get(
    "/print-jobs",
    operation_id="listPrintJobs",
    summary="Print jobs, the newest first",
    responses=problems(STAFF_ACCESS, unsafe=False),
)
async def list_print_jobs(
    _: PrinterOperator,
    service: PrintJobServiceDep,
    status_: Annotated[
        list[PrintJobStatus] | None,
        Query(alias="status", description="Only these states (repeatable)."),
    ] = None,
    printer_id: Annotated[UUID | None, Query(description="Only on this printer.")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> PrintJobListOut:
    view = await service.latest(statuses=status_ or (), printer_id=printer_id, limit=limit)
    return PrintJobListOut.from_view(view)


@router.get(
    "/print-jobs/{job_id}",
    operation_id="getPrintJob",
    summary="A print job with its plate",
    responses=problems({**STAFF_ACCESS, **_JOB_NOT_FOUND}, unsafe=False),
)
async def get_print_job(
    job_id: UUID, _: PrinterOperator, service: PrintJobServiceDep
) -> PrintJobOut:
    return job_out(await service.get(job_id))


@router.post(
    "/print-jobs",
    status_code=status.HTTP_201_CREATED,
    operation_id="createPrintJob",
    summary="Queue a plate on a printer",
    responses=problems({**STAFF_ACCESS, **_PRINTER_NOT_FOUND, 409: ["printer_retired"]}),
)
async def create_print_job(
    body: PrintJobCreateIn, staff: ProductionPlanner, service: PrintJobServiceDep
) -> PrintJobOut:
    view = await service.plan(
        printer_id=body.printer_id,
        lines=[(line.part_id, line.quantity) for line in body.lines],
        planned_minutes=body.planned_minutes,
        note=body.note,
        staff_id=staff.id,
    )
    return job_out(view)


@router.put(
    "/print-jobs/{job_id}",
    operation_id="planPrintJob",
    summary="Move a waiting job to another printer, or change its duration and note",
    responses=problems(
        {
            **STAFF_ACCESS,
            404: ["print_job_not_found", "printer_not_found"],
            409: [*_JOB_STATE, "printer_retired"],
        }
    ),
)
async def plan_print_job(
    job_id: UUID, body: PrintJobPlanIn, _: ProductionPlanner, service: PrintJobServiceDep
) -> PrintJobOut:
    view = await service.reschedule(
        job_id, printer_id=body.printer_id, planned_minutes=body.planned_minutes, note=body.note
    )
    return job_out(view)


@router.post(
    "/print-jobs/{job_id}/start",
    operation_id="startPrintJob",
    summary="The plate goes onto its printer (in service and free)",
    responses=problems(
        {**STAFF_ACCESS, **_JOB_NOT_FOUND, 409: [*_JOB_STATE, *PRINTER_UNAVAILABLE[:2]]}
    ),
)
async def start_print_job(
    job_id: UUID, staff: PrinterOperator, service: PrintJobServiceDep
) -> PrintJobOut:
    return job_out(await service.start(job_id, staff_id=staff.id))


@router.post(
    "/print-jobs/{job_id}/take-off",
    operation_id="takeOffPrintJob",
    summary="Printing is over: the parts go into post-processing, the printer is free",
    responses=problems({**STAFF_ACCESS, **_JOB_NOT_FOUND, 409: _JOB_STATE}),
)
async def take_off_print_job(
    job_id: UUID, _: PrinterOperator, service: PrintJobServiceDep
) -> PrintJobOut:
    return job_out(await service.take_off(job_id))


@router.post(
    "/print-jobs/{job_id}/complete",
    operation_id="completePrintJob",
    summary="Done: the good parts of each line, the rest failed",
    responses=problems({**STAFF_ACCESS, **_JOB_NOT_FOUND, 409: _JOB_STATE}),
)
async def complete_print_job(
    job_id: UUID, body: PrintJobCompleteIn, staff: PrinterOperator, service: PrintJobServiceDep
) -> PrintJobOut:
    view = await service.complete(
        job_id, good={line.part_id: line.good for line in body.lines}, staff_id=staff.id
    )
    return job_out(view)


@router.post(
    "/print-jobs/{job_id}/fail",
    operation_id="failPrintJob",
    summary="The whole plate is lost",
    responses=problems({**STAFF_ACCESS, **_JOB_NOT_FOUND, 409: _JOB_STATE}),
)
async def fail_print_job(
    job_id: UUID, body: PrintJobFailIn, staff: PrinterOperator, service: PrintJobServiceDep
) -> PrintJobOut:
    return job_out(await service.fail(job_id, reason=body.reason, staff_id=staff.id))


@router.post(
    "/print-jobs/{job_id}/cancel",
    operation_id="cancelPrintJob",
    summary="A waiting job is not printed after all",
    responses=problems({**STAFF_ACCESS, **_JOB_NOT_FOUND, 409: _JOB_STATE}),
)
async def cancel_print_job(
    job_id: UUID, staff: ProductionPlanner, service: PrintJobServiceDep
) -> PrintJobOut:
    return job_out(await service.cancel(job_id, staff_id=staff.id))
