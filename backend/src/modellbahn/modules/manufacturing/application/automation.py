"""Automatic planning (ADR 0034): a paid order waits for a model, the plates get queued.

Run by the worker after every backorder and once a day as a safety net. It plans only
what is missing (kits needed, less parts at hand and on open plates), so a second run, a
retried event or two orders at once plan nothing twice.
"""

from collections import defaultdict
from dataclasses import dataclass
from typing import Final
from uuid import UUID

import structlog

from modellbahn.modules.manufacturing.application.common import commit
from modellbahn.modules.manufacturing.application.ports import UnitOfWorkFactory
from modellbahn.modules.manufacturing.domain.model import JOB_NOTE_MAX_LENGTH, PrintJob
from modellbahn.modules.manufacturing.domain.planning import plan_plates, shortfall
from modellbahn.platform.clock import Clock

_logger = structlog.get_logger(__name__)

NOTE_PREFIX: Final = "Automatisch geplant"
"""How an automatic plate's note begins, so people see where it came from."""


@dataclass(frozen=True, slots=True)
class PlanningResult:
    plates: int
    """Plates queued now."""
    unplaced_parts: int
    """Parts still missing that no printer in service can print."""
    without_bom: int
    """Pieces waiting whose model has no bill of materials: nobody knows what to print."""


class AutoPlanner:
    def __init__(self, *, uow_factory: UnitOfWorkFactory, clock: Clock) -> None:
        self._uow = uow_factory
        self._clock = clock

    async def plan_waiting(self) -> PlanningResult:
        async with self._uow() as uow:
            # Every printer is locked first: two runs at once wait for each other, so the
            # second sees the plates of the first and plans nothing twice.
            printers = list(await uow.printers.all())
            for printer in printers:
                await uow.printers.get(printer.id, for_update=True)
            pieces = await uow.stock.waiting_pieces()
            if not pieces:
                return PlanningResult(plates=0, unplaced_parts=0, without_bom=0)
            scales = await uow.catalog.variant_scales({variant_id for _, variant_id in pieces})
            needed: dict[UUID, int] = defaultdict(int)
            orders_of_part: dict[UUID, list[UUID]] = defaultdict(list)
            without_bom = 0
            boms = {}
            for order_id, variant_id in pieces:
                scale_id = scales.get(variant_id)
                if scale_id is not None and scale_id not in boms:
                    boms[scale_id] = await uow.boms.get(scale_id)
                bom = boms.get(scale_id) if scale_id is not None else None
                if bom is None or not bom.lines:
                    without_bom += 1
                    continue
                for line in bom.lines:
                    needed[line.part_id] += line.quantity
                    if order_id not in orders_of_part[line.part_id]:
                        orders_of_part[line.part_id].append(order_id)
            open_jobs = await uow.jobs.open_jobs()
            on_plates: dict[UUID, int] = defaultdict(int)
            queued: dict[UUID, int] = defaultdict(int)
            for job in open_jobs:
                queued[job.printer_id] += job.planned_minutes or 60
                for job_line in job.lines:
                    on_plates[job_line.part_id] += job_line.quantity
            missing = shortfall(needed, await uow.stock.part_supply(), on_plates)
            if not missing:
                return PlanningResult(plates=0, unplaced_parts=0, without_bom=without_bom)
            parts = await uow.parts.by_ids(missing.keys())
            plan = plan_plates(
                (
                    (parts[part_id], quantity)
                    for part_id, quantity in missing.items()
                    if part_id in parts
                ),
                printers,
                queued,
            )
            numbers = await uow.stock.order_numbers(
                {order_id for ids in orders_of_part.values() for order_id in ids}
            )
            now = self._clock.now()
            for plate in plan.plates:
                orders = [numbers[o] for o in orders_of_part[plate.part.id] if o in numbers]
                note = f"{NOTE_PREFIX} für {', '.join(orders)}" if orders else NOTE_PREFIX
                job, event = PrintJob.plan(
                    number=await uow.jobs.next_number(),
                    printer=plate.printer,
                    lines=[(plate.part, plate.quantity)],
                    planned_minutes=None,
                    note=_clipped(note),
                    staff_id=None,
                    now=now,
                )
                uow.jobs.add(job)
                uow.publish(event)
            await commit(uow)
        unplaced = sum(plan.unplaced.values())
        _logger.info(
            "manufacturing.autoplan",
            plates=len(plan.plates),
            unplaced_parts=unplaced,
            without_bom=without_bom,
        )
        return PlanningResult(
            plates=len(plan.plates), unplaced_parts=unplaced, without_bom=without_bom
        )


def _clipped(note: str) -> str:
    if len(note) <= JOB_NOTE_MAX_LENGTH:
        return note
    return note[: JOB_NOTE_MAX_LENGTH - 1].rstrip(", ") + "…"
