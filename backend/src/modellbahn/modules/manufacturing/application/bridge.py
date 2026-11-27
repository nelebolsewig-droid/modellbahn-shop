"""The printer bridge (ADR 0049): the printers report themselves, nobody types a plate in.

A small program in the workshop reads every resin printer over the network and sends
what it sees here: which file prints, how far, and whether a print finished or stopped.
From that the printer hall moves by itself:

- a print starts → the plate waiting on that printer with the part of the file starts,
  otherwise a new plate for the part; a file no part has made yet makes its part first,
  and what the print tells (time, resin) fills what the part lacks (ADR 0050);
- a print finished → the plate goes to post-processing (the good parts are still counted
  by hand when the plate is done, that books them into stock);
- a print stopped → the plate failed.

Every report says the whole state, so a lost or repeated report changes nothing: the
printer's own id of a print (``task_id``) is booked once.
"""

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
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
    LAYER_HEIGHT_UM_RANGE,
    MATERIAL_PER_PART_MAX,
    NOTES_MAX_LENGTH,
    PART_NAME_MAX_LENGTH,
    PART_NUMBER_MAX_LENGTH,
    PARTS_PER_PLATE_MAX,
    PLATE_MINUTES_MAX,
    Part,
    PartDetails,
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
    volume_ml: float | None = None
    """Resin of the whole plate, if the bridge found the sliced file (ADR 0050)."""
    layer_height_um: int | None = None


class Outcome(StrEnum):
    UNKNOWN_PRINTER = "unknown_printer"
    NOT_IN_SERVICE = "not_in_service"
    UNMATCHED = "unmatched"
    """A print whose file name gives no part (no letters or digits): nothing booked."""
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
        """The waiting plate with the part the file names, or a new plate for it.

        A file that names no part yet makes its part first (ADR 0050).
        """
        parts = await uow.parts.search(
            scale_code=None,
            technology=printer.technology.value,
            query=None,
            include_archived=False,
            limit=PARTS_SEARCHED,
        )
        part = match_part(report.slice_file, parts) or await self._new_part(uow, printer, report)
        if part is None:
            return None
        self._learn(part, report)
        queue = sorted(
            await uow.jobs.latest(
                statuses=[PrintJobStatus.QUEUED],
                printer_id=printer.id,
                part_id=part.id,
                limit=PARTS_SEARCHED,
            ),
            key=lambda job: job.number,
        )
        if queue:
            return queue[0]
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

    async def _new_part(
        self, uow: ManufacturingUnitOfWork, printer: Printer, report: PrinterReport
    ) -> Part | None:
        """A part made from the file name: number and name from it, the printer's resin."""
        stem = file_stem(report.slice_file)
        count = parts_on_plate(stem)
        stem = _COUNT.sub(" ", stem).strip(" _-.") or stem
        base = part_number_from(stem)
        if not base:
            return None
        scales = await uow.catalog.scale_names()
        if not scales:
            return None
        number = base
        suffix = 2
        while await uow.parts.number_taken(number):
            tail = f"-{suffix}"
            number = base[: PART_NUMBER_MAX_LENGTH - len(tail)].rstrip("-") + tail
            suffix += 1
        materials = [
            m for m in await uow.materials.all() if m.active and m.technology is printer.technology
        ]
        details = PartDetails(
            part_number=number,
            name=stem[:PART_NAME_MAX_LENGTH],
            material_id=materials[0].id if materials else None,
            parts_per_plate=count,
            notes=f"Automatisch angelegt aus der Druckdatei „{_file(report)}“."[:NOTES_MAX_LENGTH],
        ).checked()
        part = Part.create(
            details,
            scale_code=scale_from(stem, scales),
            technology=printer.technology,
            material=materials[0] if materials else None,
            now=self._clock.now(),
        )
        uow.parts.add(part)
        return part

    def _learn(self, part: Part, report: PrinterReport) -> None:
        """What a part lacks and the print tells: its plate time, its resin per part."""
        now = self._clock.now()
        if part.plate_minutes is None and (minutes := _minutes(report)):
            part.plate_minutes = minutes
            part.updated_at = now
        if part.material_per_part is None and report.volume_ml:
            each = Decimal(str(report.volume_ml)) / part.parts_per_plate
            if Decimal("0.01") <= each <= MATERIAL_PER_PART_MAX:
                part.material_per_part = each.quantize(Decimal("0.01"))
                part.updated_at = now
        if part.layer_height_um is None and report.layer_height_um:
            low, high = LAYER_HEIGHT_UM_RANGE
            if low <= report.layer_height_um <= high:
                part.layer_height_um = report.layer_height_um
                part.updated_at = now


_SLICE_SUFFIXES: Final = (".ctb", ".goo", ".pwmx", ".prz", ".jxs", ".cbddlp", ".photon")
_COUNT: Final = re.compile(
    r"(?:^|(?<=[^A-Z0-9]))(?:X\s?(\d{1,3})|(\d{1,3})\s?X)(?=[^A-Z0-9]|$)", re.IGNORECASE
)


_CHITUBOX_TAIL: Final = re.compile(r"[_ ]0\.\d{2,3}_\d+(?:\.\d+)?(?:_\d{2,4}){5}$")
"""Layer height, exposure, date and time Chitubox appends to a plate's name."""


def file_stem(slice_file: str) -> str:
    """``BR_99_23-24_dummy.stl #4.ctb`` → ``BR_99_23-24_dummy``: the model, not the plate."""
    name = slice_file.strip().replace("\\", "/").rsplit("/", 1)[-1]
    lower = name.lower()
    for suffix in _SLICE_SUFFIXES:
        if lower.endswith(suffix):
            name = name[: -len(suffix)]
            break
    name = name.split("#", 1)[0].strip()
    # Chitubox: ``v10c_tür_32.stl_0.040_4.000_2026_11_25_11_01``: the model ends at .stl.
    name = re.split(r"\.(?:stl|obj|3mf)(?![A-Za-z0-9])", name, maxsplit=1, flags=re.IGNORECASE)[0]
    name = _CHITUBOX_TAIL.sub("", name)
    return name.strip(" _-.")


def part_number_from(stem: str) -> str:
    """Letters and digits of the file name, joined by single hyphens, upper case."""
    plain = stem.upper().replace("Ä", "AE").replace("Ö", "OE").replace("Ü", "UE").replace("ß", "SS")
    number = "-".join(re.findall(r"[A-Z0-9]+", plain))
    return number[:PART_NUMBER_MAX_LENGTH].rstrip("-")


def parts_on_plate(stem: str) -> int:
    """``x4`` or ``4x`` in the file name is the count on the plate; otherwise one."""
    found = _COUNT.search(stem)
    count = int(found.group(1) or found.group(2)) if found else 1
    return min(max(count, 1), PARTS_PER_PLATE_MAX)


def scale_from(stem: str, scales: Mapping[str, str]) -> str:
    """The scale the file name names (``…_H0``); otherwise H0, the shop's usual one."""
    tokens = set(re.findall(r"[A-Z0-9]+", stem.upper()))
    named = [code for code in scales if code.upper() in tokens]
    if named:
        return max(named, key=len)
    return "H0" if "H0" in scales else sorted(scales)[0]


def _file(report: PrinterReport) -> str:
    return report.slice_file.strip().rsplit("/", 1)[-1][:SLICE_FILE_MAX_LENGTH]


def _minutes(report: PrinterReport) -> int | None:
    """The whole print in minutes, from the time gone and the time left the printer knows."""
    if report.remaining_seconds is None:
        return None
    total = report.remaining_seconds + (report.elapsed_seconds or 0)
    return min(max(round(total / 60), 1), PLATE_MINUTES_MAX)
