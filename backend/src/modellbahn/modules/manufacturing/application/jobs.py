"""Use cases around the print jobs: plan a plate, move it, start it, report how it went."""

from collections.abc import Awaitable, Callable, Collection, Mapping, Sequence
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
    PrintJobNotFoundError,
)
from modellbahn.modules.manufacturing.domain.model import (
    Part,
    Printer,
    PrintJob,
    PrintJobStatus,
)
from modellbahn.platform.clock import Clock
from modellbahn.platform.events import DomainEvent

JOBS_LISTED_MAX: Final = 200

type _Step = Callable[[ManufacturingUnitOfWork, PrintJob, Printer], Awaitable[DomainEvent]]


@dataclass(frozen=True, slots=True)
class JobView:
    """Jobs with what it takes to show them: their printers and the parts on their plates."""

    jobs: Sequence[PrintJob]
    printers: Mapping[UUID, Printer]
    parts: Mapping[UUID, Part]

    @property
    def job(self) -> PrintJob:
        (job,) = self.jobs
        return job


class PrintJobService:
    def __init__(self, *, uow_factory: UnitOfWorkFactory, clock: Clock) -> None:
        self._uow = uow_factory
        self._clock = clock

    async def latest(
        self,
        *,
        statuses: Collection[PrintJobStatus] = (),
        printer_id: UUID | None = None,
        limit: int = JOBS_LISTED_MAX,
    ) -> JobView:
        async with self._uow() as uow:
            jobs = await uow.jobs.latest(
                statuses=statuses,
                printer_id=printer_id,
                part_id=None,
                limit=min(limit, JOBS_LISTED_MAX),
            )
            return await _view(uow, jobs)

    async def get(self, job_id: UUID) -> JobView:
        async with self._uow() as uow:
            return await _view(uow, [await _job(uow, job_id)])

    async def plan(
        self,
        *,
        printer_id: UUID,
        lines: Sequence[tuple[UUID, int]],
        planned_minutes: int | None,
        note: str,
        staff_id: UUID | None,
    ) -> JobView:
        """Queue a plate on a printer; without a duration it is estimated from the parts."""
        async with self._uow() as uow:
            printer = await _printer(uow, printer_id)
            parts = await uow.parts.by_ids({part_id for part_id, _ in lines})
            resolved: list[tuple[Part, int]] = []
            for index, (part_id, quantity) in enumerate(lines):
                part = parts.get(part_id)
                if part is None:
                    raise InvalidFieldError(f"lines.{index}.part_id", "unknown", "no such part")
                resolved.append((part, quantity))
            job, event = PrintJob.plan(
                number=await uow.jobs.next_number(),
                printer=printer,
                lines=resolved,
                planned_minutes=planned_minutes,
                note=note,
                staff_id=staff_id,
                now=self._clock.now(),
            )
            uow.jobs.add(job)
            uow.publish(event)
            await commit(uow)
            return await _view(uow, [job])

    async def reschedule(
        self, job_id: UUID, *, printer_id: UUID, planned_minutes: int | None, note: str
    ) -> JobView:
        async with self._uow() as uow:
            job = await _job(uow, job_id, for_update=True)
            printer = await _printer(uow, printer_id)
            uow.publish(
                job.reschedule(
                    printer=printer,
                    planned_minutes=planned_minutes,
                    note=note,
                    now=self._clock.now(),
                )
            )
            await commit(uow)
            return await _view(uow, [job])

    async def start(self, job_id: UUID, *, staff_id: UUID | None) -> JobView:
        async def step(
            uow: ManufacturingUnitOfWork, job: PrintJob, printer: Printer
        ) -> DomainEvent:
            running = await uow.jobs.printing_on(printer.id)
            return job.start(
                printer, busy=running is not None, staff_id=staff_id, now=self._clock.now()
            )

        return await self._step(job_id, step)

    async def take_off(self, job_id: UUID) -> JobView:
        async def step(
            uow: ManufacturingUnitOfWork, job: PrintJob, printer: Printer
        ) -> DomainEvent:
            return job.take_off(printer, now=self._clock.now())

        return await self._step(job_id, step)

    async def complete(
        self, job_id: UUID, *, good: Mapping[UUID, int], staff_id: UUID | None
    ) -> JobView:
        """Done; ``good`` names the good parts per part, parts not named all came out well."""

        async def step(
            uow: ManufacturingUnitOfWork, job: PrintJob, printer: Printer
        ) -> DomainEvent:
            return job.complete(printer, good=good, staff_id=staff_id, now=self._clock.now())

        return await self._step(job_id, step)

    async def fail(self, job_id: UUID, *, reason: str, staff_id: UUID | None) -> JobView:
        async def step(
            uow: ManufacturingUnitOfWork, job: PrintJob, printer: Printer
        ) -> DomainEvent:
            return job.fail(printer, reason=reason, staff_id=staff_id, now=self._clock.now())

        return await self._step(job_id, step)

    async def cancel(self, job_id: UUID, *, staff_id: UUID | None) -> JobView:
        async def step(
            uow: ManufacturingUnitOfWork, job: PrintJob, printer: Printer
        ) -> DomainEvent:
            return job.cancel(printer, staff_id=staff_id, now=self._clock.now())

        return await self._step(job_id, step)

    async def _step(self, job_id: UUID, step: _Step) -> JobView:
        async with self._uow() as uow:
            # The printer is locked before the job, as a report about the printer does:
            # a defect and a start on the same printer then wait for each other.
            printer = await _printer(uow, (await _job(uow, job_id)).printer_id, for_update=True)
            job = await _job(uow, job_id, for_update=True)
            if job.printer_id != printer.id:
                # Moved to another printer in the meantime: that one counts now.
                printer = await _printer(uow, job.printer_id, for_update=True)
            uow.publish(await step(uow, job, printer))
            await commit(uow)
            return await _view(uow, [job])


async def _view(uow: ManufacturingUnitOfWork, jobs: Sequence[PrintJob]) -> JobView:
    printers = await uow.printers.by_ids({job.printer_id for job in jobs})
    return JobView(jobs=jobs, printers=printers, parts=await parts_of(uow, jobs))


async def _job(uow: ManufacturingUnitOfWork, job_id: UUID, *, for_update: bool = False) -> PrintJob:
    job = await uow.jobs.get(job_id, for_update=for_update)
    if job is None:
        raise PrintJobNotFoundError
    return job


async def _printer(
    uow: ManufacturingUnitOfWork, printer_id: UUID, *, for_update: bool = False
) -> Printer:
    printer = await uow.printers.get(printer_id, for_update=for_update)
    if printer is None:
        raise PrinterNotFoundError
    return printer
