"""The manufacturing model: the workshop's printers, what is printed on them, and what a kit is.

A *printer* has a code on its label (``D03``), a technology (filament or resin) and a
state: in service, defective, in repair, or retired. Every report of a state is kept with
who made it and why, so the hall can say "defekt seit Dienstag: Düse verstopft" and each
printer's history stays readable. Whether a printer prints is not stored: it prints while
one of its jobs is printing.

A *material* is what a printer is loaded with; it belongs to one technology.

A *part* is one printable piece for one scale, with its print data: layer height, minutes
for a full plate, parts per plate, material per part. Scale and technology are fixed once
the part exists; a part for another scale is another part.

A *bill of materials* says which parts in which quantities make a product in one scale.
Every variant of it (kit or finished model, in any colour) shares it: painting comes after
printing. It only takes parts of its own scale.

A *print job* is one plate on one printer:

    queued ──▶ printing ──▶ post_processing ──▶ done
      │           │  └─────────────────────────▲
      ▼           ▼              ▼
  cancelled     failed ◀─────────┘

A job waits in the printer's queue and starts only on a printer in service, and at most
one job prints on a printer at a time. Post-processing (washing, curing, removing
supports) happens off the printer, which is free again by then. Completing a job reports
the good parts of each line; the rest count as failed.

Plain dataclasses without any framework, mapped imperatively by the infrastructure.
Every method that depends on time takes ``now``.
"""

import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from enum import StrEnum
from typing import Final
from uuid import UUID

from modellbahn.modules.manufacturing.domain.errors import (
    InvalidFieldError,
    InvalidPrintJobStateError,
    PrinterUnavailableError,
)
from modellbahn.modules.manufacturing.domain.events import (
    PrinterStatusChanged,
    PrintJobChanged,
    PrintJobCompleted,
    PrintJobFailed,
)
from modellbahn.platform.ids import new_id

PRINTER_CODE: Final = re.compile(r"[A-Z0-9]{1,8}")
PRINTER_CODE_MAX_LENGTH: Final = 8
PRINTER_NAME_MAX_LENGTH: Final = 60
PRINTER_MODEL_MAX_LENGTH: Final = 80
BUILD_MM_MAX: Final = 2000
STATUS_NOTE_MAX_LENGTH: Final = 200
NOTES_MAX_LENGTH: Final = 500

MATERIAL_NAME_MAX_LENGTH: Final = 60

PART_NUMBER: Final = re.compile(r"[A-Z0-9]+(?:-[A-Z0-9]+)*")
PART_NUMBER_MAX_LENGTH: Final = 40
PART_NAME_MAX_LENGTH: Final = 120
LAYER_HEIGHT_UM_RANGE: Final = (10, 1000)
PLATE_MINUTES_MAX: Final = 10_080  # a week
PARTS_PER_PLATE_MAX: Final = 1000
MATERIAL_PER_PART_MAX: Final = Decimal("100000")

BOM_QUANTITY_MAX: Final = 999
BOM_LINES_MAX: Final = 200

JOB_QUANTITY_MAX: Final = 1000
JOB_LINES_MAX: Final = 50
JOB_NOTE_MAX_LENGTH: Final = 500
FAILURE_REASON_MAX_LENGTH: Final = 200


def _text(value: str, field_name: str, max_length: int, *, required: bool = False) -> str:
    cleaned = " ".join(value.split())
    if required and not cleaned:
        raise InvalidFieldError(field_name, "required", "must not be empty")
    if len(cleaned) > max_length:
        raise InvalidFieldError(field_name, "too_long", f"at most {max_length} characters")
    return cleaned


def _multiline(value: str, field_name: str, max_length: int) -> str:
    lines = [" ".join(line.split()) for line in value.strip().splitlines()]
    cleaned = "\n".join(line for line in lines if line)
    if len(cleaned) > max_length:
        raise InvalidFieldError(field_name, "too_long", f"at most {max_length} characters")
    return cleaned


def _in_range(value: int | None, field_name: str, low: int, high: int) -> int | None:
    if value is not None and not low <= value <= high:
        raise InvalidFieldError(field_name, "out_of_range", f"between {low} and {high}")
    return value


class Technology(StrEnum):
    FDM = "fdm"
    """Filament, layer by layer from a nozzle: time grows with every part on the plate."""
    RESIN = "resin"
    """Resin cured by light, a whole layer at once: the tallest part sets the time."""


# --- Printers -------------------------------------------------------------------------


class PrinterStatus(StrEnum):
    IN_SERVICE = "in_service"
    DEFECTIVE = "defective"
    IN_REPAIR = "in_repair"
    RETIRED = "retired"


@dataclass(frozen=True, slots=True)
class PrinterDetails:
    """What staff fill in for a printer, checked and normalised by :meth:`checked`."""

    code: str
    name: str = ""
    model: str = ""
    build_x_mm: int | None = None
    build_y_mm: int | None = None
    build_z_mm: int | None = None
    notes: str = ""

    def checked(self) -> "PrinterDetails":
        code = self.code.strip().upper()
        if not PRINTER_CODE.fullmatch(code):
            raise InvalidFieldError("code", "invalid", "1 to 8 letters or digits")
        volume = (self.build_x_mm, self.build_y_mm, self.build_z_mm)
        if any(size is None for size in volume) and any(size is not None for size in volume):
            raise InvalidFieldError("build_z_mm", "incomplete", "all three sizes or none")
        for name, size in zip(("build_x_mm", "build_y_mm", "build_z_mm"), volume, strict=True):
            _in_range(size, name, 1, BUILD_MM_MAX)
        return PrinterDetails(
            code=code,
            name=_text(self.name, "name", PRINTER_NAME_MAX_LENGTH),
            model=_text(self.model, "model", PRINTER_MODEL_MAX_LENGTH),
            build_x_mm=self.build_x_mm,
            build_y_mm=self.build_y_mm,
            build_z_mm=self.build_z_mm,
            notes=_multiline(self.notes, "notes", NOTES_MAX_LENGTH),
        )


@dataclass(eq=False, kw_only=True)
class StatusReport:
    """One entry of a printer's history: its new state, why, and who reported it."""

    id: UUID
    printer_id: UUID
    from_status: PrinterStatus | None
    """``None`` for the first entry, when the printer was added."""
    to_status: PrinterStatus
    note: str
    staff_id: UUID | None
    occurred_at: datetime


@dataclass(eq=False, kw_only=True)
class Printer:
    """One printer of the workshop."""

    id: UUID
    code: str
    name: str
    model: str
    technology: Technology
    build_x_mm: int | None
    build_y_mm: int | None
    build_z_mm: int | None
    notes: str
    status: PrinterStatus
    status_note: str
    status_changed_at: datetime
    created_at: datetime
    updated_at: datetime

    @classmethod
    def create(
        cls,
        details: PrinterDetails,
        *,
        technology: Technology,
        staff_id: UUID | None,
        now: datetime,
    ) -> tuple["Printer", StatusReport, PrinterStatusChanged]:
        """A printer in service; its history starts with that."""
        checked = details.checked()
        printer = cls(
            id=new_id(),
            code=checked.code,
            name="",
            model="",
            technology=technology,
            build_x_mm=None,
            build_y_mm=None,
            build_z_mm=None,
            notes="",
            status=PrinterStatus.IN_SERVICE,
            status_note="",
            status_changed_at=now,
            created_at=now,
            updated_at=now,
        )
        printer.change(checked, now)
        report = StatusReport(
            id=new_id(),
            printer_id=printer.id,
            from_status=None,
            to_status=PrinterStatus.IN_SERVICE,
            note="",
            staff_id=staff_id,
            occurred_at=now,
        )
        event = PrinterStatusChanged(
            aggregate_id=printer.id,
            occurred_at=now,
            code=printer.code,
            status=printer.status.value,
            previous_status=None,
        )
        return printer, report, event

    def change(self, details: PrinterDetails, now: datetime) -> None:
        """Name, model, build volume, notes and the code on its label; not the technology."""
        checked = details.checked()
        self.code = checked.code
        self.name = checked.name
        self.model = checked.model
        self.build_x_mm = checked.build_x_mm
        self.build_y_mm = checked.build_y_mm
        self.build_z_mm = checked.build_z_mm
        self.notes = checked.notes
        self.updated_at = now

    @property
    def label(self) -> str:
        """``D03 · Saturn links``, or the code alone."""
        return f"{self.code} · {self.name}" if self.name else self.code

    @property
    def in_service(self) -> bool:
        return self.status is PrinterStatus.IN_SERVICE

    def report(
        self,
        status: PrinterStatus,
        *,
        note: str,
        printing: bool,
        queued: int,
        staff_id: UUID | None,
        now: datetime,
    ) -> tuple[StatusReport, PrinterStatusChanged] | None:
        """Someone reports the printer's state; ``None`` if nothing changes.

        Reporting the same state again with another note keeps the state and records the
        note (``defekt: Ersatzteil bestellt``). A printing printer can only break down:
        the caller then fails the job that was printing. Repair and retirement wait until
        nothing prints, and retirement until no job waits for the printer.
        """
        cleaned = _text(note, "note", STATUS_NOTE_MAX_LENGTH)
        if status is self.status and cleaned == self.status_note:
            return None
        if printing and status not in {PrinterStatus.IN_SERVICE, PrinterStatus.DEFECTIVE}:
            raise PrinterUnavailableError("busy")
        if status is PrinterStatus.RETIRED and queued:
            raise PrinterUnavailableError("has_queue")
        previous = self.status
        self.status = status
        self.status_note = cleaned
        self.updated_at = now
        if status is not previous:
            self.status_changed_at = now
        report = StatusReport(
            id=new_id(),
            printer_id=self.id,
            from_status=previous,
            to_status=status,
            note=cleaned,
            staff_id=staff_id,
            occurred_at=now,
        )
        event = PrinterStatusChanged(
            aggregate_id=self.id,
            occurred_at=now,
            code=self.code,
            status=status.value,
            previous_status=previous.value,
        )
        return report, event


# --- Materials ------------------------------------------------------------------------


@dataclass(eq=False, kw_only=True)
class Material:
    """A filament or a resin, as the workshop calls it (``PLA grau``, ``Resin ABS-like``)."""

    id: UUID
    name: str
    technology: Technology
    notes: str
    active: bool
    created_at: datetime
    updated_at: datetime

    @classmethod
    def create(cls, *, name: str, technology: Technology, notes: str, now: datetime) -> "Material":
        material = cls(
            id=new_id(),
            name="",
            technology=technology,
            notes="",
            active=True,
            created_at=now,
            updated_at=now,
        )
        material.change(name=name, notes=notes, active=True, now=now)
        return material

    def change(self, *, name: str, notes: str, active: bool, now: datetime) -> None:
        self.name = _text(name, "name", MATERIAL_NAME_MAX_LENGTH, required=True)
        self.notes = _multiline(notes, "notes", NOTES_MAX_LENGTH)
        self.active = active
        self.updated_at = now


# --- Parts ----------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class PartDetails:
    """What staff fill in for a part, besides its scale and technology."""

    part_number: str
    name: str
    material_id: UUID | None = None
    layer_height_um: int | None = None
    plate_minutes: int | None = None
    """How long a full plate of this part prints."""
    parts_per_plate: int = 1
    material_per_part: Decimal | None = None
    """Grams of filament or millilitres of resin for one part, supports included."""
    notes: str = ""

    def checked(self) -> "PartDetails":
        number = self.part_number.strip().upper()
        if len(number) > PART_NUMBER_MAX_LENGTH or not PART_NUMBER.fullmatch(number):
            raise InvalidFieldError(
                "part_number",
                "invalid",
                f"letters, digits and single hyphens, at most {PART_NUMBER_MAX_LENGTH}",
            )
        _in_range(self.layer_height_um, "layer_height_um", *LAYER_HEIGHT_UM_RANGE)
        _in_range(self.plate_minutes, "plate_minutes", 1, PLATE_MINUTES_MAX)
        _in_range(self.parts_per_plate, "parts_per_plate", 1, PARTS_PER_PLATE_MAX)
        amount = self.material_per_part
        if amount is not None and not Decimal("0.01") <= amount <= MATERIAL_PER_PART_MAX:
            raise InvalidFieldError(
                "material_per_part", "out_of_range", f"between 0.01 and {MATERIAL_PER_PART_MAX}"
            )
        return PartDetails(
            part_number=number,
            name=_text(self.name, "name", PART_NAME_MAX_LENGTH, required=True),
            material_id=self.material_id,
            layer_height_um=self.layer_height_um,
            plate_minutes=self.plate_minutes,
            parts_per_plate=self.parts_per_plate,
            material_per_part=amount.quantize(Decimal("0.01")) if amount is not None else None,
            notes=_multiline(self.notes, "notes", NOTES_MAX_LENGTH),
        )


@dataclass(eq=False, kw_only=True)
class Part:
    """One printable piece for one scale: ``STW-ALT-DACH-H0``, the roof of a signal box."""

    id: UUID
    part_number: str
    name: str
    scale_code: str
    technology: Technology
    material_id: UUID | None
    layer_height_um: int | None
    plate_minutes: int | None
    parts_per_plate: int
    material_per_part: Decimal | None
    notes: str
    active: bool
    created_at: datetime
    updated_at: datetime

    @classmethod
    def create(
        cls,
        details: PartDetails,
        *,
        scale_code: str,
        technology: Technology,
        material: Material | None,
        now: datetime,
    ) -> "Part":
        part = cls(
            id=new_id(),
            part_number="",
            name="",
            scale_code=scale_code,
            technology=technology,
            material_id=None,
            layer_height_um=None,
            plate_minutes=None,
            parts_per_plate=1,
            material_per_part=None,
            notes="",
            active=True,
            created_at=now,
            updated_at=now,
        )
        part.change(details, material=material, active=True, now=now)
        return part

    def change(
        self, details: PartDetails, *, material: Material | None, active: bool, now: datetime
    ) -> None:
        checked = details.checked()
        if (material.id if material is not None else None) != checked.material_id:
            msg = "the material passed is not the one the details name"
            raise ValueError(msg)
        if material is not None and material.technology is not self.technology:
            raise InvalidFieldError(
                "material_id", "wrong_technology", "a material for another technology"
            )
        self.part_number = checked.part_number
        self.name = checked.name
        self.material_id = checked.material_id
        self.layer_height_um = checked.layer_height_um
        self.plate_minutes = checked.plate_minutes
        self.parts_per_plate = checked.parts_per_plate
        self.material_per_part = checked.material_per_part
        self.notes = checked.notes
        self.active = active
        self.updated_at = now

    @property
    def minutes_per_part(self) -> float | None:
        """A full plate's time shared by its parts; what one more part adds on filament."""
        if self.plate_minutes is None:
            return None
        return self.plate_minutes / self.parts_per_plate


def _checked_lines(
    lines: Sequence[tuple[Part, int]], *, max_lines: int, max_quantity: int
) -> list[tuple[Part, int]]:
    if len(lines) > max_lines:
        raise InvalidFieldError("lines", "too_many", f"at most {max_lines} parts")
    seen: set[UUID] = set()
    for index, (part, quantity) in enumerate(lines):
        if part.id in seen:
            raise InvalidFieldError(f"lines.{index}.part_id", "duplicate", "listed twice")
        seen.add(part.id)
        if not 1 <= quantity <= max_quantity:
            raise InvalidFieldError(
                f"lines.{index}.quantity", "out_of_range", f"between 1 and {max_quantity}"
            )
    return list(lines)


# --- Bills of materials ---------------------------------------------------------------


@dataclass(eq=False, kw_only=True)
class BomLine:
    product_scale_id: UUID
    part_id: UUID
    scale_code: str
    quantity: int
    position: int


@dataclass(eq=False, kw_only=True)
class BillOfMaterials:
    """The parts of a product in one scale: one building, one roof, two chimneys."""

    product_scale_id: UUID
    scale_code: str
    updated_at: datetime
    updated_by: UUID | None
    lines: list[BomLine] = field(default_factory=list)

    @classmethod
    def start(
        cls, *, product_scale_id: UUID, scale_code: str, staff_id: UUID | None, now: datetime
    ) -> "BillOfMaterials":
        return cls(
            product_scale_id=product_scale_id,
            scale_code=scale_code,
            updated_at=now,
            updated_by=staff_id,
        )

    def replace(
        self, lines: Sequence[tuple[Part, int]], *, staff_id: UUID | None, now: datetime
    ) -> None:
        """Set all lines at once, in the order given; only parts of this scale."""
        checked = _checked_lines(lines, max_lines=BOM_LINES_MAX, max_quantity=BOM_QUANTITY_MAX)
        for index, (part, _) in enumerate(checked):
            if part.scale_code != self.scale_code:
                raise InvalidFieldError(
                    f"lines.{index}.part_id", "wrong_scale", f"not a part for {self.scale_code}"
                )
        kept = {line.part_id: line for line in self.lines}
        replaced: list[BomLine] = []
        for position, (part, quantity) in enumerate(checked):
            # Lines that stay are updated in place: the session then updates their rows
            # instead of deleting and inserting the same primary key.
            line = kept.get(part.id) or BomLine(
                product_scale_id=self.product_scale_id,
                part_id=part.id,
                scale_code=self.scale_code,
                quantity=quantity,
                position=position,
            )
            line.quantity = quantity
            line.position = position
            replaced.append(line)
        self.lines[:] = replaced
        self.updated_at = now
        self.updated_by = staff_id

    @property
    def part_count(self) -> int:
        return sum(line.quantity for line in self.lines)


# --- Print jobs -----------------------------------------------------------------------


class PrintJobStatus(StrEnum):
    QUEUED = "queued"
    PRINTING = "printing"
    POST_PROCESSING = "post_processing"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"


OPEN_JOB_STATUSES: Final = frozenset(
    {PrintJobStatus.QUEUED, PrintJobStatus.PRINTING, PrintJobStatus.POST_PROCESSING}
)


def estimate_minutes(technology: Technology, lines: Sequence[tuple[Part, int]]) -> int | None:
    """How long a plate with these parts prints, from their print data; ``None`` if unknown.

    On filament every part adds its share of a full plate's time. On resin the light
    cures a whole layer at once, so the part that takes longest sets the time. The
    slicer knows better; this is the estimate until someone enters its figure.
    """
    if not lines or any(part.plate_minutes is None for part, _ in lines):
        return None
    if technology is Technology.RESIN:
        return max(part.plate_minutes or 0 for part, _ in lines)
    total = sum((part.minutes_per_part or 0) * quantity for part, quantity in lines)
    return max(1, math.ceil(total - 1e-9))


@dataclass(eq=False, kw_only=True)
class PrintJobLine:
    job_id: UUID
    part_id: UUID
    technology: Technology
    quantity: int
    good: int
    failed: int
    position: int


@dataclass(eq=False, kw_only=True)
class PrintJob:
    """One plate on one printer, numbered for people (``Druck 17``)."""

    id: UUID
    number: int
    printer_id: UUID
    technology: Technology
    status: PrintJobStatus
    planned_minutes: int | None
    """How long it should print: entered from the slicer, or estimated from the parts."""
    note: str
    failure_reason: str
    created_by: UUID | None
    created_at: datetime
    started_at: datetime | None
    started_by: UUID | None
    printed_at: datetime | None
    """When it came off the printer (into post-processing, or straight to done)."""
    finished_at: datetime | None
    finished_by: UUID | None
    updated_at: datetime
    lines: list[PrintJobLine] = field(default_factory=list)

    @classmethod
    def plan(
        cls,
        *,
        number: int,
        printer: Printer,
        lines: Sequence[tuple[Part, int]],
        planned_minutes: int | None,
        note: str,
        staff_id: UUID | None,
        now: datetime,
    ) -> tuple["PrintJob", PrintJobChanged]:
        """Queue a plate on ``printer``: parts of its technology, each once with a quantity."""
        if printer.status is PrinterStatus.RETIRED:
            raise PrinterUnavailableError("retired")
        if not lines:
            raise InvalidFieldError("lines", "required", "at least one part")
        checked = _checked_lines(lines, max_lines=JOB_LINES_MAX, max_quantity=JOB_QUANTITY_MAX)
        for index, (part, _) in enumerate(checked):
            if part.technology is not printer.technology:
                raise InvalidFieldError(
                    f"lines.{index}.part_id", "wrong_technology", "not for this printer"
                )
            if not part.active:
                raise InvalidFieldError(f"lines.{index}.part_id", "archived", "archived")
        job_id = new_id()
        job = cls(
            id=job_id,
            number=number,
            printer_id=printer.id,
            technology=printer.technology,
            status=PrintJobStatus.QUEUED,
            planned_minutes=None,
            note=_multiline(note, "note", JOB_NOTE_MAX_LENGTH),
            failure_reason="",
            created_by=staff_id,
            created_at=now,
            started_at=None,
            started_by=None,
            printed_at=None,
            finished_at=None,
            finished_by=None,
            updated_at=now,
            lines=[
                PrintJobLine(
                    job_id=job_id,
                    part_id=part.id,
                    technology=printer.technology,
                    quantity=quantity,
                    good=0,
                    failed=0,
                    position=position,
                )
                for position, (part, quantity) in enumerate(checked)
            ],
        )
        job.planned_minutes = (
            _planned(planned_minutes)
            if planned_minutes is not None
            else estimate_minutes(printer.technology, checked)
        )
        return job, job._changed(printer, "queued", now)

    @property
    def is_open(self) -> bool:
        return self.status in OPEN_JOB_STATUSES

    @property
    def part_count(self) -> int:
        return sum(line.quantity for line in self.lines)

    @property
    def expected_end(self) -> datetime | None:
        """When printing should be over, if it is printing and its duration is known."""
        if self.started_at is None or self.planned_minutes is None:
            return None
        return self.started_at + timedelta(minutes=self.planned_minutes)

    def reschedule(
        self, *, printer: Printer, planned_minutes: int | None, note: str, now: datetime
    ) -> PrintJobChanged:
        """Move a waiting job to another printer of its technology, or change its plan."""
        self._require(PrintJobStatus.QUEUED)
        if printer.technology is not self.technology:
            raise InvalidFieldError("printer_id", "wrong_technology", "a printer for other parts")
        if printer.status is PrinterStatus.RETIRED:
            raise PrinterUnavailableError("retired")
        self.printer_id = printer.id
        self.planned_minutes = _planned(planned_minutes) if planned_minutes is not None else None
        self.note = _multiline(note, "note", JOB_NOTE_MAX_LENGTH)
        self.updated_at = now
        return self._changed(printer, "rescheduled", now)

    def start(
        self, printer: Printer, *, busy: bool, staff_id: UUID | None, now: datetime
    ) -> PrintJobChanged:
        """The plate goes onto its printer, which must be in service and free."""
        self._require(PrintJobStatus.QUEUED)
        if printer.id != self.printer_id:
            msg = "the job is queued on another printer"
            raise ValueError(msg)
        if not printer.in_service:
            raise PrinterUnavailableError("not_in_service")
        if busy:
            raise PrinterUnavailableError("busy")
        self.status = PrintJobStatus.PRINTING
        self.started_at = now
        self.started_by = staff_id
        self.updated_at = now
        return self._changed(printer, "started", now)

    def take_off(self, printer: Printer, *, now: datetime) -> PrintJobChanged:
        """Printing is over; the parts are washed, cured or cleaned. The printer is free."""
        self._require(PrintJobStatus.PRINTING)
        self.status = PrintJobStatus.POST_PROCESSING
        self.printed_at = now
        self.updated_at = now
        return self._changed(printer, "printed", now)

    def complete(
        self,
        printer: Printer,
        *,
        good: Mapping[UUID, int],
        staff_id: UUID | None,
        now: datetime,
    ) -> PrintJobCompleted:
        """Done: ``good`` parts of each line (by part), the rest of the line failed."""
        self._require(PrintJobStatus.PRINTING, PrintJobStatus.POST_PROCESSING)
        unknown = set(good) - {line.part_id for line in self.lines}
        if unknown:
            raise InvalidFieldError("lines", "unknown_part", "a part that is not on the plate")
        for index, line in enumerate(self.lines):
            count = good.get(line.part_id, line.quantity)
            if not 0 <= count <= line.quantity:
                raise InvalidFieldError(
                    f"lines.{index}.good", "out_of_range", f"between 0 and {line.quantity}"
                )
        for line in self.lines:
            line.good = good.get(line.part_id, line.quantity)
            line.failed = line.quantity - line.good
        self.status = PrintJobStatus.DONE
        self.printed_at = self.printed_at or now
        self.finished_at = now
        self.finished_by = staff_id
        self.updated_at = now
        return PrintJobCompleted(
            aggregate_id=self.id,
            occurred_at=now,
            number=self.number,
            printer_id=self.printer_id,
            printer_code=printer.code,
            status=self.status.value,
            good_parts=sum(line.good for line in self.lines),
            failed_parts=sum(line.failed for line in self.lines),
        )

    def fail(
        self, printer: Printer, *, reason: str, staff_id: UUID | None, now: datetime
    ) -> PrintJobFailed:
        """The whole plate is lost, on the printer or in post-processing."""
        self._require(PrintJobStatus.PRINTING, PrintJobStatus.POST_PROCESSING)
        self.failure_reason = _text(reason, "reason", FAILURE_REASON_MAX_LENGTH)
        for line in self.lines:
            line.good = 0
            line.failed = line.quantity
        self.status = PrintJobStatus.FAILED
        self.finished_at = now
        self.finished_by = staff_id
        self.updated_at = now
        return PrintJobFailed(
            aggregate_id=self.id,
            occurred_at=now,
            number=self.number,
            printer_id=self.printer_id,
            printer_code=printer.code,
            status=self.status.value,
            reason=self.failure_reason,
        )

    def cancel(self, printer: Printer, *, staff_id: UUID | None, now: datetime) -> PrintJobChanged:
        """A waiting job is not printed after all."""
        self._require(PrintJobStatus.QUEUED)
        self.status = PrintJobStatus.CANCELLED
        self.finished_at = now
        self.finished_by = staff_id
        self.updated_at = now
        return self._changed(printer, "cancelled", now)

    def _require(self, *statuses: PrintJobStatus) -> None:
        if self.status not in statuses:
            raise InvalidPrintJobStateError(self.status.value)

    def _changed(self, printer: Printer, change: str, now: datetime) -> PrintJobChanged:
        return PrintJobChanged(
            aggregate_id=self.id,
            occurred_at=now,
            number=self.number,
            printer_id=self.printer_id,
            printer_code=printer.code,
            status=self.status.value,
            change=change,
        )


def _planned(minutes: int) -> int:
    _in_range(minutes, "planned_minutes", 1, PLATE_MINUTES_MAX)
    return minutes
