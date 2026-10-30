"""Use cases around the printers: the hall with every printer's state and plate, and reports.

A report of a defect while a plate prints ends that plate as failed, in the same
transaction: the printer is broken, so nothing prints on it any more.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Final
from uuid import UUID

from modellbahn.modules.manufacturing.application.common import commit, parts_of
from modellbahn.modules.manufacturing.application.ports import (
    ManufacturingUnitOfWork,
    UnitOfWorkFactory,
)
from modellbahn.modules.manufacturing.domain.errors import (
    InvalidFieldError,
    PrinterNotFoundError,
)
from modellbahn.modules.manufacturing.domain.model import (
    Part,
    Printer,
    PrinterDetails,
    PrinterStatus,
    PrintJob,
    PrintJobStatus,
    StatusReport,
    Technology,
)
from modellbahn.platform.clock import Clock

HISTORY_SHOWN: Final = 30
RECENT_JOBS_SHOWN: Final = 20


@dataclass(frozen=True, slots=True)
class PrinterDesk:
    """A printer in the hall: its state, the plate on it, and what waits for it."""

    printer: Printer
    printing: PrintJob | None
    queue: Sequence[PrintJob]


@dataclass(frozen=True, slots=True)
class Hall:
    """Every printer with its plates, the plates in post-processing, and their parts."""

    desks: Sequence[PrinterDesk]
    post_processing: Sequence[PrintJob]
    parts: Mapping[UUID, Part]

    @property
    def printers(self) -> dict[UUID, Printer]:
        return {desk.printer.id: desk.printer for desk in self.desks}


@dataclass(frozen=True, slots=True)
class PrinterRecord:
    """One printer with its history: status reports with their reporters, latest plates."""

    desk: PrinterDesk
    history: Sequence[StatusReport]
    names: Mapping[UUID, str]
    jobs: Sequence[PrintJob]
    parts: Mapping[UUID, Part]


class PrinterService:
    def __init__(self, *, uow_factory: UnitOfWorkFactory, clock: Clock) -> None:
        self._uow = uow_factory
        self._clock = clock

    async def hall(self) -> Hall:
        async with self._uow() as uow:
            printers = await uow.printers.all()
            jobs = await uow.jobs.open_jobs()
            parts = await parts_of(uow, jobs)
        printing = {job.printer_id: job for job in jobs if job.status is PrintJobStatus.PRINTING}
        queues: dict[UUID, list[PrintJob]] = {}
        for job in jobs:
            if job.status is PrintJobStatus.QUEUED:
                queues.setdefault(job.printer_id, []).append(job)
        return Hall(
            desks=[
                PrinterDesk(
                    printer=printer,
                    printing=printing.get(printer.id),
                    queue=queues.get(printer.id, []),
                )
                for printer in printers
            ],
            post_processing=[job for job in jobs if job.status is PrintJobStatus.POST_PROCESSING],
            parts=parts,
        )

    async def record(self, printer_id: UUID) -> PrinterRecord:
        async with self._uow() as uow:
            printer = await _printer(uow, printer_id)
            history = await uow.printers.history(printer.id, HISTORY_SHOWN)
            names = await uow.staff.names(
                {report.staff_id for report in history if report.staff_id is not None}
            )
            jobs = await uow.jobs.latest(
                statuses=(), printer_id=printer.id, part_id=None, limit=RECENT_JOBS_SHOWN
            )
            open_jobs = [job for job in await uow.jobs.open_jobs() if job.printer_id == printer.id]
            parts = await parts_of(uow, [*jobs, *open_jobs])
        desk = PrinterDesk(
            printer=printer,
            printing=next(
                (job for job in open_jobs if job.status is PrintJobStatus.PRINTING), None
            ),
            queue=[job for job in open_jobs if job.status is PrintJobStatus.QUEUED],
        )
        return PrinterRecord(desk=desk, history=history, names=names, jobs=jobs, parts=parts)

    async def create(
        self, details: PrinterDetails, *, technology: Technology, staff_id: UUID | None
    ) -> Printer:
        async with self._uow() as uow:
            checked = details.checked()
            await _check_code(uow, checked.code, except_id=None)
            printer, report, event = Printer.create(
                checked, technology=technology, staff_id=staff_id, now=self._clock.now()
            )
            uow.printers.add(printer)
            # The report refers to the printer: the printer's row goes in first.
            await uow.flush()
            uow.printers.record(report)
            uow.publish(event)
            await commit(uow)
        return printer

    async def change(self, printer_id: UUID, details: PrinterDetails) -> Printer:
        async with self._uow() as uow:
            printer = await _printer(uow, printer_id, for_update=True)
            checked = details.checked()
            await _check_code(uow, checked.code, except_id=printer.id)
            printer.change(checked, self._clock.now())
            await commit(uow)
        return printer

    async def delete(self, printer_id: UUID) -> None:
        """Only a printer that never had a job; any other keeps its history (retire it)."""
        async with self._uow() as uow:
            printer = await _printer(uow, printer_id, for_update=True)
            await uow.printers.delete(printer)
            await commit(uow)

    async def report(
        self, printer_id: UUID, status: PrinterStatus, *, note: str, staff_id: UUID | None
    ) -> Printer:
        """Record the printer's state; a defect ends the plate printing on it as failed."""
        now = self._clock.now()
        async with self._uow() as uow:
            printer = await _printer(uow, printer_id, for_update=True)
            printing = await uow.jobs.printing_on(printer.id, for_update=True)
            reported = printer.report(
                status,
                note=note,
                printing=printing is not None,
                queued=await uow.jobs.queued_count(printer.id),
                staff_id=staff_id,
                now=now,
            )
            if reported is None:
                return printer
            report, event = reported
            uow.printers.record(report)
            uow.publish(event)
            if printing is not None and status is PrinterStatus.DEFECTIVE:
                reason = f"Drucker defekt: {report.note}" if report.note else "Drucker defekt"
                uow.publish(printing.fail(printer, reason=reason, staff_id=staff_id, now=now))
            await commit(uow)
        return printer


async def _printer(
    uow: ManufacturingUnitOfWork, printer_id: UUID, *, for_update: bool = False
) -> Printer:
    printer = await uow.printers.get(printer_id, for_update=for_update)
    if printer is None:
        raise PrinterNotFoundError
    return printer


async def _check_code(uow: ManufacturingUnitOfWork, code: str, *, except_id: UUID | None) -> None:
    if await uow.printers.code_taken(code, except_id=except_id):
        raise InvalidFieldError("code", "duplicate", "another printer has it")
