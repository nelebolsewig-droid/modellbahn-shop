"""Request and response bodies of the manufacturing API (snake_case JSON)."""

from collections.abc import Mapping, Sequence
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from modellbahn.modules.catalog.contracts.product_scales import ProductScaleLabel
from modellbahn.modules.manufacturing.application.jobs import JobView
from modellbahn.modules.manufacturing.application.parts import (
    BomView,
    MaterialEntry,
    PartEntry,
    PartRecord,
)
from modellbahn.modules.manufacturing.application.printers import (
    Hall,
    PrinterDesk,
    PrinterRecord,
)
from modellbahn.modules.manufacturing.domain.model import (
    BOM_LINES_MAX,
    BOM_QUANTITY_MAX,
    BUILD_MM_MAX,
    FAILURE_REASON_MAX_LENGTH,
    JOB_LINES_MAX,
    JOB_NOTE_MAX_LENGTH,
    JOB_QUANTITY_MAX,
    LAYER_HEIGHT_UM_RANGE,
    MATERIAL_NAME_MAX_LENGTH,
    NOTES_MAX_LENGTH,
    PART_NAME_MAX_LENGTH,
    PART_NUMBER_MAX_LENGTH,
    PARTS_PER_PLATE_MAX,
    PLATE_MINUTES_MAX,
    PRINTER_CODE_MAX_LENGTH,
    PRINTER_MODEL_MAX_LENGTH,
    PRINTER_NAME_MAX_LENGTH,
    STATUS_NOTE_MAX_LENGTH,
    Part,
    PartDetails,
    Printer,
    PrinterDetails,
    PrinterStatus,
    PrintJob,
    PrintJobStatus,
    StatusReport,
    Technology,
)


class _Request(BaseModel):
    model_config = ConfigDict(extra="forbid")


BuildMillimetres = Annotated[int, Field(ge=1, le=BUILD_MM_MAX)]
PlateMinutes = Annotated[int, Field(ge=1, le=PLATE_MINUTES_MAX, examples=[190])]


# --- Printers -------------------------------------------------------------------------


class PrinterRefOut(BaseModel):
    id: UUID
    code: str = Field(examples=["D03"])
    name: str = Field(examples=["Saturn links"])


class PrinterOut(PrinterRefOut):
    model: str = Field(examples=["Elegoo Saturn 4 Ultra"])
    technology: Technology
    build_x_mm: int | None = Field(examples=[218])
    build_y_mm: int | None = Field(examples=[123])
    build_z_mm: int | None = Field(examples=[220])
    notes: str
    status: PrinterStatus
    status_note: str = Field(
        description="Why it is in this state.", examples=["Düse verstopft, Ersatz bestellt"]
    )
    status_changed_at: datetime = Field(description="Since when it is in this state.")
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_printer(cls, printer: Printer) -> Self:
        return cls(
            id=printer.id,
            code=printer.code,
            name=printer.name,
            model=printer.model,
            technology=printer.technology,
            build_x_mm=printer.build_x_mm,
            build_y_mm=printer.build_y_mm,
            build_z_mm=printer.build_z_mm,
            notes=printer.notes,
            status=printer.status,
            status_note=printer.status_note,
            status_changed_at=printer.status_changed_at,
            created_at=printer.created_at,
            updated_at=printer.updated_at,
        )


class PartRefOut(BaseModel):
    id: UUID
    part_number: str = Field(examples=["STW-ALT-DACH-H0"])
    name: str = Field(examples=["Dach Stellwerk Altenau"])
    scale_code: str = Field(examples=["H0"])


def _part_ref(part: Part) -> PartRefOut:
    return PartRefOut(
        id=part.id, part_number=part.part_number, name=part.name, scale_code=part.scale_code
    )


class PrintJobLineOut(BaseModel):
    part: PartRefOut
    quantity: int = Field(description="Planned on the plate.")
    good: int = Field(description="Came out well (once the job is done).")
    failed: int


class PrintJobOut(BaseModel):
    id: UUID
    number: int = Field(examples=[17], description="Shown as „Druck 17“.")
    printer: PrinterRefOut
    technology: Technology
    status: PrintJobStatus
    planned_minutes: int | None = Field(
        description="How long it prints: from the slicer, or estimated from the parts."
    )
    expected_end_at: datetime | None = Field(
        description="When printing should be over (set once it started)."
    )
    note: str
    failure_reason: str
    part_count: int
    created_at: datetime
    started_at: datetime | None
    printed_at: datetime | None = Field(description="When it came off the printer.")
    finished_at: datetime | None
    lines: list[PrintJobLineOut]

    @classmethod
    def from_job(
        cls, job: PrintJob, *, printers: Mapping[UUID, Printer], parts: Mapping[UUID, Part]
    ) -> Self:
        printer = printers[job.printer_id]
        return cls(
            id=job.id,
            number=job.number,
            printer=PrinterRefOut(id=printer.id, code=printer.code, name=printer.name),
            technology=job.technology,
            status=job.status,
            planned_minutes=job.planned_minutes,
            expected_end_at=job.expected_end,
            note=job.note,
            failure_reason=job.failure_reason,
            part_count=job.part_count,
            created_at=job.created_at,
            started_at=job.started_at,
            printed_at=job.printed_at,
            finished_at=job.finished_at,
            lines=[
                PrintJobLineOut(
                    part=_part_ref(parts[line.part_id]),
                    quantity=line.quantity,
                    good=line.good,
                    failed=line.failed,
                )
                for line in job.lines
            ],
        )


def _jobs_out(
    jobs: Sequence[PrintJob], printers: Mapping[UUID, Printer], parts: Mapping[UUID, Part]
) -> list[PrintJobOut]:
    return [PrintJobOut.from_job(job, printers=printers, parts=parts) for job in jobs]


class PrinterDeskOut(PrinterOut):
    printing: PrintJobOut | None = Field(description="The plate on the printer right now.")
    queue: list[PrintJobOut] = Field(description="Waiting for the printer, the oldest first.")

    @classmethod
    def from_desk(
        cls, desk: PrinterDesk, *, printers: Mapping[UUID, Printer], parts: Mapping[UUID, Part]
    ) -> Self:
        return cls(
            **PrinterOut.from_printer(desk.printer).model_dump(),
            printing=(
                PrintJobOut.from_job(desk.printing, printers=printers, parts=parts)
                if desk.printing is not None
                else None
            ),
            queue=_jobs_out(desk.queue, printers, parts),
        )


class HallCountsOut(BaseModel):
    in_service: int
    defective: int
    in_repair: int
    retired: int
    printing: int
    queued: int
    post_processing: int


class HallOut(BaseModel):
    """The printer hall: every printer with its plate and queue, and the plates after it."""

    printers: list[PrinterDeskOut] = Field(description="By code.")
    post_processing: list[PrintJobOut] = Field(
        description="Off the printer, being washed, cured or cleaned; the oldest first."
    )
    counts: HallCountsOut

    @classmethod
    def from_hall(cls, hall: Hall) -> Self:
        printers = hall.printers
        statuses = [desk.printer.status for desk in hall.desks]
        return cls(
            printers=[
                PrinterDeskOut.from_desk(desk, printers=printers, parts=hall.parts)
                for desk in hall.desks
            ],
            post_processing=_jobs_out(hall.post_processing, printers, hall.parts),
            counts=HallCountsOut(
                in_service=statuses.count(PrinterStatus.IN_SERVICE),
                defective=statuses.count(PrinterStatus.DEFECTIVE),
                in_repair=statuses.count(PrinterStatus.IN_REPAIR),
                retired=statuses.count(PrinterStatus.RETIRED),
                printing=sum(1 for desk in hall.desks if desk.printing is not None),
                queued=sum(len(desk.queue) for desk in hall.desks),
                post_processing=len(hall.post_processing),
            ),
        )


class StatusReportOut(BaseModel):
    id: UUID
    from_status: PrinterStatus | None = Field(description="Null for the printer's first entry.")
    to_status: PrinterStatus
    note: str
    staff_name: str | None = Field(description="Who reported it, if known.")
    occurred_at: datetime

    @classmethod
    def from_report(cls, report: StatusReport, names: Mapping[UUID, str]) -> Self:
        return cls(
            id=report.id,
            from_status=report.from_status,
            to_status=report.to_status,
            note=report.note,
            staff_name=names.get(report.staff_id) if report.staff_id is not None else None,
            occurred_at=report.occurred_at,
        )


class PrinterRecordOut(PrinterDeskOut):
    history: list[StatusReportOut] = Field(description="Status reports, the newest first.")
    jobs: list[PrintJobOut] = Field(description="Its latest plates, the newest first.")

    @classmethod
    def from_record(cls, record: PrinterRecord) -> Self:
        printers = {record.desk.printer.id: record.desk.printer}
        return cls(
            **PrinterDeskOut.from_desk(
                record.desk, printers=printers, parts=record.parts
            ).model_dump(),
            history=[
                StatusReportOut.from_report(report, record.names) for report in record.history
            ],
            jobs=_jobs_out(record.jobs, printers, record.parts),
        )


class PrinterIn(_Request):
    """Everything about a printer but its technology; editing sends all of it again."""

    code: str = Field(min_length=1, max_length=PRINTER_CODE_MAX_LENGTH, examples=["D03"])
    name: str = Field(default="", max_length=PRINTER_NAME_MAX_LENGTH, examples=["Saturn links"])
    model: str = Field(default="", max_length=PRINTER_MODEL_MAX_LENGTH)
    build_x_mm: BuildMillimetres | None = None
    build_y_mm: BuildMillimetres | None = None
    build_z_mm: BuildMillimetres | None = None
    notes: str = Field(default="", max_length=NOTES_MAX_LENGTH)

    def details(self) -> PrinterDetails:
        return PrinterDetails(
            code=self.code,
            name=self.name,
            model=self.model,
            build_x_mm=self.build_x_mm,
            build_y_mm=self.build_y_mm,
            build_z_mm=self.build_z_mm,
            notes=self.notes,
        )


class PrinterCreateIn(PrinterIn):
    technology: Technology = Field(description="Fixed once the printer exists.")


class PrinterStatusIn(_Request):
    status: PrinterStatus
    note: str = Field(
        default="",
        max_length=STATUS_NOTE_MAX_LENGTH,
        description="Why; the same status with a new note records the note.",
        examples=["Düse verstopft"],
    )


# --- Materials ------------------------------------------------------------------------


class MaterialRefOut(BaseModel):
    id: UUID
    name: str = Field(examples=["PLA grau"])


class MaterialOut(MaterialRefOut):
    technology: Technology
    notes: str
    active: bool
    part_count: int = Field(description="Parts made of it.")

    @classmethod
    def from_entry(cls, entry: MaterialEntry) -> Self:
        material = entry.material
        return cls(
            id=material.id,
            name=material.name,
            technology=material.technology,
            notes=material.notes,
            active=material.active,
            part_count=entry.parts,
        )


class MaterialListOut(BaseModel):
    items: list[MaterialOut]


class MaterialIn(_Request):
    name: str = Field(min_length=1, max_length=MATERIAL_NAME_MAX_LENGTH)
    notes: str = Field(default="", max_length=NOTES_MAX_LENGTH)
    active: bool = True


class MaterialCreateIn(_Request):
    name: str = Field(min_length=1, max_length=MATERIAL_NAME_MAX_LENGTH, examples=["PLA grau"])
    technology: Technology = Field(description="Fixed once the material exists.")
    notes: str = Field(default="", max_length=NOTES_MAX_LENGTH)


# --- Parts ----------------------------------------------------------------------------


class PartOut(PartRefOut):
    scale_name: str = Field(examples=["H0"])
    technology: Technology
    material: MaterialRefOut | None
    layer_height_um: int | None = Field(examples=[50])
    plate_minutes: int | None = Field(description="A full plate of this part.")
    parts_per_plate: int
    minutes_per_part: float | None = Field(
        description="A full plate's time shared by its parts (one decimal)."
    )
    material_per_part: float | None = Field(
        description="Grams of filament or millilitres of resin, supports included."
    )
    notes: str
    active: bool
    bom_count: int = Field(description="Kits whose bill of materials names it.")
    job_count: int = Field(description="Plates it was or is on.")
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_entry(cls, entry: PartEntry) -> Self:
        part = entry.part
        minutes = part.minutes_per_part
        return cls(
            id=part.id,
            part_number=part.part_number,
            name=part.name,
            scale_code=part.scale_code,
            scale_name=entry.scale_name,
            technology=part.technology,
            material=(
                MaterialRefOut(id=entry.material.id, name=entry.material.name)
                if entry.material is not None
                else None
            ),
            layer_height_um=part.layer_height_um,
            plate_minutes=part.plate_minutes,
            parts_per_plate=part.parts_per_plate,
            minutes_per_part=round(minutes, 1) if minutes is not None else None,
            material_per_part=(
                float(part.material_per_part) if part.material_per_part is not None else None
            ),
            notes=part.notes,
            active=part.active,
            bom_count=entry.usage.boms,
            job_count=entry.usage.jobs,
            created_at=part.created_at,
            updated_at=part.updated_at,
        )


class PartListOut(BaseModel):
    items: list[PartOut] = Field(description="By scale and part number, at most 500.")


class ProductScaleRefOut(BaseModel):
    product_scale_id: UUID
    product_id: UUID
    product_number: int
    product_name: str = Field(examples=["Stellwerk Altenau"])
    scale_code: str
    scale_name: str


class PartUseOut(BaseModel):
    product_scale: ProductScaleRefOut
    quantity: int


class PartRecordOut(PartOut):
    uses: list[PartUseOut] = Field(description="The kits that need it, by product.")
    jobs: list[PrintJobOut] = Field(description="Its latest plates, the newest first.")

    @classmethod
    def from_record(cls, record: PartRecord) -> Self:
        return cls(
            **PartOut.from_entry(record.entry).model_dump(),
            uses=[
                PartUseOut(
                    product_scale=_product_scale_ref(use.product_scale), quantity=use.quantity
                )
                for use in record.uses
            ],
            jobs=_jobs_out(record.jobs, record.printers, record.parts),
        )


class PartIn(_Request):
    """Everything about a part but its scale and technology; editing sends all of it again."""

    part_number: str = Field(
        min_length=1, max_length=PART_NUMBER_MAX_LENGTH, examples=["STW-ALT-DACH-H0"]
    )
    name: str = Field(min_length=1, max_length=PART_NAME_MAX_LENGTH)
    material_id: UUID | None = None
    layer_height_um: (
        Annotated[int, Field(ge=LAYER_HEIGHT_UM_RANGE[0], le=LAYER_HEIGHT_UM_RANGE[1])] | None
    ) = None
    plate_minutes: PlateMinutes | None = None
    parts_per_plate: Annotated[int, Field(ge=1, le=PARTS_PER_PLATE_MAX)] = 1
    material_per_part: Annotated[float, Field(gt=0, le=100_000)] | None = None
    notes: str = Field(default="", max_length=NOTES_MAX_LENGTH)
    active: bool = True

    def details(self) -> PartDetails:
        return PartDetails(
            part_number=self.part_number,
            name=self.name,
            material_id=self.material_id,
            layer_height_um=self.layer_height_um,
            plate_minutes=self.plate_minutes,
            parts_per_plate=self.parts_per_plate,
            material_per_part=(
                Decimal(str(round(self.material_per_part, 2)))
                if self.material_per_part is not None
                else None
            ),
            notes=self.notes,
        )


class PartCreateIn(PartIn):
    scale_code: str = Field(min_length=1, max_length=4, examples=["H0"])
    technology: Technology


# --- Bills of materials ---------------------------------------------------------------


def _product_scale_ref(label: ProductScaleLabel) -> ProductScaleRefOut:
    return ProductScaleRefOut(
        product_scale_id=label.product_scale_id,
        product_id=label.product_id,
        product_number=label.product_number,
        product_name=label.product_name,
        scale_code=label.scale_code,
        scale_name=label.scale_name,
    )


class BomLineOut(BaseModel):
    part: PartRefOut
    technology: Technology
    quantity: int
    plate_minutes: int | None
    parts_per_plate: int
    active: bool = Field(description="False once the part is archived.")


class BomOut(BaseModel):
    """A product in one scale with the parts it is made of; no lines while it has none."""

    product_scale: ProductScaleRefOut
    lines: list[BomLineOut]
    part_count: int = Field(description="Parts of one kit, all lines added up.")
    print_minutes: int | None = Field(
        description="Printing time of one kit, each part's share of a full plate; null "
        "while a part has no plate time."
    )
    updated_at: datetime | None

    @classmethod
    def from_view(cls, view: BomView) -> Self:
        lines = view.bom.lines if view.bom is not None else []
        return cls(
            product_scale=_product_scale_ref(view.product_scale),
            lines=[
                BomLineOut(
                    part=_part_ref(view.parts[line.part_id]),
                    technology=view.parts[line.part_id].technology,
                    quantity=line.quantity,
                    plate_minutes=view.parts[line.part_id].plate_minutes,
                    parts_per_plate=view.parts[line.part_id].parts_per_plate,
                    active=view.parts[line.part_id].active,
                )
                for line in lines
            ],
            part_count=view.part_count,
            print_minutes=view.print_minutes,
            updated_at=view.bom.updated_at if view.bom is not None else None,
        )


class BomLineIn(_Request):
    part_id: UUID
    quantity: Annotated[int, Field(ge=1, le=BOM_QUANTITY_MAX)] = 1


class BomIn(_Request):
    lines: list[BomLineIn] = Field(
        max_length=BOM_LINES_MAX, description="All parts in their order; empty removes it."
    )


# --- Print jobs -----------------------------------------------------------------------


class PrintJobListOut(BaseModel):
    items: list[PrintJobOut] = Field(description="The newest first.")

    @classmethod
    def from_view(cls, view: JobView) -> Self:
        return cls(items=_jobs_out(view.jobs, view.printers, view.parts))


def job_out(view: JobView) -> PrintJobOut:
    return PrintJobOut.from_job(view.job, printers=view.printers, parts=view.parts)


class PrintJobLineIn(_Request):
    part_id: UUID
    quantity: Annotated[int, Field(ge=1, le=JOB_QUANTITY_MAX)] = 1


class PrintJobCreateIn(_Request):
    printer_id: UUID
    lines: list[PrintJobLineIn] = Field(min_length=1, max_length=JOB_LINES_MAX)
    planned_minutes: PlateMinutes | None = Field(
        default=None, description="From the slicer; empty: estimated from the parts."
    )
    note: str = Field(default="", max_length=JOB_NOTE_MAX_LENGTH)


class PrintJobPlanIn(_Request):
    """A waiting job: another printer of its technology, its duration, its note."""

    printer_id: UUID
    planned_minutes: PlateMinutes | None = None
    note: str = Field(default="", max_length=JOB_NOTE_MAX_LENGTH)


class GoodPartsIn(_Request):
    part_id: UUID
    good: Annotated[int, Field(ge=0, le=JOB_QUANTITY_MAX)]


class PrintJobCompleteIn(_Request):
    lines: list[GoodPartsIn] = Field(
        default_factory=list,
        max_length=JOB_LINES_MAX,
        description="Good parts per part; parts not named all came out well.",
    )


class PrintJobFailIn(_Request):
    reason: str = Field(default="", max_length=FAILURE_REASON_MAX_LENGTH, examples=["Haftung"])
