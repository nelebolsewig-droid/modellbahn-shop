"""The printer bridge (ADR 0047): the printers report themselves, nobody types a plate in.

A small program in the workshop reads every resin printer over the network and sends
what it sees here: which file prints, how far, and whether a print finished or stopped.
From that the printer hall moves by itself:

- a print starts → the plate waiting on that printer with the part of the file starts,
  otherwise a waiting plate of that printer, otherwise a new plate for the part;
- a print finished → the plate goes to post-processing (the good parts are still counted
  by hand when the plate is done, that books them into stock);
- a print stopped → the plate failed.

Every report says the whole state, so a lost or repeated report changes nothing: the
printer's own id of a print (``task_id``) is booked once.
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

import structlog

from modellbahn.modules.manufacturing.application.common import commit
from modellbahn.modules.manufacturing.application.ports import (
    ManufacturingUnitOfWork,
    UnitOfWorkFactory,
)
from modellbahn.modules.manufacturing.domain.model import (
    JOB_NOTE_MAX_LENGTH,
    PLATE_MINUTES_MAX,
    Part,
    Printer,
    PrintJob,
    PrintJobStatus,
)
from modellbahn.platform.clock import Clock

_logger = structlog.get_logger(__name__)

NOTE_PREFIX: Final = "Vom Drucker gemeldet"
STOPPED_REASON: Final = "Am Drucker abgebrochen"
PARTS_SEARCHED: Final = 1000
SLICE_FILE_MAX_LENGTH: Final = 255
TASK_ID_MAX_LENGTH: Final = 100


class BridgeState(StrEnum):
    IDLE = "idle"
    PRINTING = "printing"
    FINISHED = "finished"
    STOPPED = "stopped"


@dataclass(frozen=True, slots=True)
class PrinterReport:
    """What the bridge saw on one printer."""

    code: str
    """The printer's code in the hall (``D01``), as set up in the bridge."""
    state: BridgeState
    task_id: str = ""
    slice_file: str = ""
    elapsed_seconds: int | None = None
    remaining_seconds: int | None = None
    error: str = ""


class Outcome(StrEnum):
    UNKNOWN_PRINTER = "unknown_printer"
    NOT_IN_SERVICE = "not_in_service"
    UNMATCHED = "unmatched"
    """A print with no plate waiting and a file that names no part: nothing booked."""
    STARTED = "started"
    PRINTING = "printing"
    PRINTED = "printed"
    FAILED = "failed"
    ALREADY_BOOKED = "already_booked"
    NOTHING = "nothing"


@dataclass(frozen=True, slots=True)
class ReportResult:
    code: str
    outcome: Outcome
    job_number: int | None = None


def _normalized(text: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", text.upper())


def match_part(slice_file: str, parts: Sequence[Part]) -> Part | None:
    """The part whose number the file name carries; the longest number wins.

    ``STW-ALT-DACH-H0 x8.ctb`` and ``stw_alt_dach_h0.ctb`` both name ``STW-ALT-DACH-H0``.
    """
    name = _normalized(slice_file.rsplit("/", 1)[-1])
    found = [part for part in parts if _normalized(part.part_number) in name]
    if not found:
        return None
    return max(found, key=lambda part: len(_normalized(part.part_number)))


class PrinterBridgeService:
    def __init__(self, *, uow_factory: UnitOfWorkFactory, clock: Clock) -> None:
        self._uow = uow_factory
        self._clock = clock

    async def sync(self, reports: Sequence[PrinterReport]) -> list[ReportResult]:
        results: list[ReportResult] = []
        for report in reports:
            async with self._uow() as uow:
                result = await self._one(uow, report)
                await commit(uow)
            if result.outcome not in {Outcome.PRINTING, Outcome.NOTHING}:
                _logger.info(
                    "printer_bridge_report",
                    code=report.code,
                    state=report.state.value,
                    outcome=result.outcome.value,
                    job=result.job_number,
                )
            results.append(result)
        return results

    async def _one(self, uow: ManufacturingUnitOfWork, report: PrinterReport) -> ReportResult:
        code = report.code.strip().upper()
        known = next((p for p in await uow.printers.all() if p.code.upper() == code), None)
        printer = known and await uow.printers.get(known.id, for_update=True)
        if printer is None:
            return ReportResult(code, Outcome.UNKNOWN_PRINTER)
        running = await uow.jobs.printing_on(printer.id, for_update=True)
        task_id = report.task_id.strip()[:TASK_ID_MAX_LENGTH]
        if running is not None and task_id and running.printer_task_id not in {None, task_id}:
            # Another print runs than the one booked: the old one ended unseen.
            uow.publish(running.take_off(printer, now=self._clock.now()))
            running = None
        if report.state is BridgeState.PRINTING:
            return await self._printing(uow, printer, running, report, task_id)
        if running is None:
            return ReportResult(code, Outcome.NOTHING)
        now = self._clock.now()
        if report.state is BridgeState.FINISHED:
            uow.publish(running.take_off(printer, now=now))
            return ReportResult(code, Outcome.PRINTED, running.number)
        if report.state is BridgeState.STOPPED:
            error = report.error.strip()
            reason = f"{STOPPED_REASON}: {error}" if error else STOPPED_REASON
            uow.publish(running.fail(printer, reason=reason[:200], staff_id=None, now=now))
            return ReportResult(code, Outcome.FAILED, running.number)
        return ReportResult(code, Outcome.PRINTING, running.number)

    async def _printing(
        self,
        uow: ManufacturingUnitOfWork,
        printer: Printer,
        running: PrintJob | None,
        report: PrinterReport,
        task_id: str,
    ) -> ReportResult:
        code = printer.code
        if running is not None:
            if running.printer_task_id is None and task_id:
                running.printer_task_id = task_id
                running.slice_file = running.slice_file or _file(report)
                running.updated_at = self._clock.now()
            return ReportResult(code, Outcome.PRINTING, running.number)
        if task_id and (booked := await uow.jobs.by_task_id(task_id)) is not None:
            return ReportResult(code, Outcome.ALREADY_BOOKED, booked.number)
        if not printer.in_service:
            return ReportResult(code, Outcome.NOT_IN_SERVICE)
        job = await self._plate_for(uow, printer, report)
        if job is None:
            return ReportResult(code, Outcome.UNMATCHED)
        job.slice_file = _file(report)
        job.printer_task_id = task_id or None
        if minutes := _minutes(report):
            job.planned_minutes = minutes
        uow.publish(job.start(printer, busy=False, staff_id=None, now=self._clock.now()))
        return ReportResult(code, Outcome.STARTED, job.number)

    async def _plate_for(
        self, uow: ManufacturingUnitOfWork, printer: Printer, report: PrinterReport
    ) -> PrintJob | None:
        """The waiting plate this print is, or a new one for the part the file names."""
        parts = await uow.parts.search(
            scale_code=None,
            technology=printer.technology.value,
            query=None,
            include_archived=False,
            limit=PARTS_SEARCHED,
        )
        part = match_part(report.slice_file, parts)
        queue = sorted(
            await uow.jobs.latest(
                statuses=[PrintJobStatus.QUEUED],
                printer_id=printer.id,
                part_id=None,
                limit=PARTS_SEARCHED,
            ),
            key=lambda job: job.number,
        )
        if part is not None:
            with_part = [j for j in queue if any(ln.part_id == part.id for ln in j.lines)]
            if with_part:
                return with_part[0]
            job, event = PrintJob.plan(
                number=await uow.jobs.next_number(),
                printer=printer,
                lines=[(part, part.parts_per_plate)],
                planned_minutes=None,
                note=f"{NOTE_PREFIX}: {_file(report)}"[:JOB_NOTE_MAX_LENGTH],
                staff_id=None,
                now=self._clock.now(),
            )
            uow.jobs.add(job)
            uow.publish(event)
            return job
        return queue[0] if queue else None


def _file(report: PrinterReport) -> str:
    return report.slice_file.strip().rsplit("/", 1)[-1][:SLICE_FILE_MAX_LENGTH]


def _minutes(report: PrinterReport) -> int | None:
    """The whole print in minutes, from the time gone and the time left the printer knows."""
    if report.remaining_seconds is None:
        return None
    total = report.remaining_seconds + (report.elapsed_seconds or 0)
    return min(max(round(total / 60), 1), PLATE_MINUTES_MAX)
