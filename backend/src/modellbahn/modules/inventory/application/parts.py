"""Use cases of the parts store: receiving finished plates, counting boxes, looking parts up.

* **Receiving** (*Wareneingang*): when a plate is done, its good parts arrive as one
  receipt per part (the worker runs this on ``manufacturing.print_job.completed``).
  Scanning a box and then the part's label puts them away (see :mod:`.scanning`); what
  never reaches a shelf is written off.
* **Counting**: after counting a box, its quantity is set to what was counted; the
  journal books the difference.
* **Looking up**: every part with its boxes, what is still in receiving, its history.
"""

from collections import defaultdict
from dataclasses import dataclass
from typing import Final
from uuid import UUID

import structlog

from modellbahn.modules.inventory.application.common import (
    PartJournal,
    UnitOfWorkFactory,
    resolve_location,
)
from modellbahn.modules.inventory.application.ports import InventoryUnitOfWork
from modellbahn.modules.inventory.domain.errors import PartNotFoundError, ReceiptNotFoundError
from modellbahn.modules.inventory.domain.events import PartsArrived
from modellbahn.modules.inventory.domain.model import Location
from modellbahn.modules.inventory.domain.parts import PartLedgerEntry, PartReceipt, PartStock
from modellbahn.modules.manufacturing.contracts.parts import PartInfo, PrintJobInfo
from modellbahn.platform.clock import Clock
from modellbahn.platform.uow import UniqueViolationError

HISTORY_LIMIT: Final = 50

_logger = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class LocatedParts:
    location: Location
    quantity: int


@dataclass(frozen=True, slots=True)
class PartStockLine:
    """One part: how many lie where (walking order), and how many wait in receiving."""

    part: PartInfo
    total: int
    incoming: int
    locations: list[LocatedParts]


@dataclass(frozen=True, slots=True)
class ReceiptView:
    receipt: PartReceipt
    part: PartInfo | None
    job: PrintJobInfo | None


@dataclass(frozen=True, slots=True)
class PartHistoryEntry:
    entry: PartLedgerEntry
    from_location: Location | None
    to_location: Location | None
    staff_name: str | None
    job_number: int | None
    unit_code: str | None


@dataclass(frozen=True, slots=True)
class PartDetails:
    line: PartStockLine
    receipts: list[ReceiptView]
    """Still in receiving, oldest first."""
    history: list[PartHistoryEntry]
    """Newest first, at most :data:`HISTORY_LIMIT`."""


def walking_order(stock: list[PartStock], locations: dict[UUID, Location]) -> list[PartStock]:
    """``stock`` ordered by the path of its locations, the way one walks the shelves."""
    return sorted(
        stock,
        key=lambda entry: (
            locations[entry.location_id].path if entry.location_id in locations else "",
            entry.location_id,
        ),
    )


async def stock_lines(
    uow: InventoryUnitOfWork, parts: dict[UUID, PartInfo], receipts: list[PartReceipt]
) -> list[PartStockLine]:
    """The lines of ``parts``, by part number."""
    stock = await uow.part_stock.for_parts(parts)
    locations = await uow.locations.by_ids({entry.location_id for entry in stock})
    by_part: defaultdict[UUID, list[PartStock]] = defaultdict(list)
    for entry in walking_order(stock, locations):
        by_part[entry.part_id].append(entry)
    incoming: defaultdict[UUID, int] = defaultdict(int)
    for receipt in receipts:
        incoming[receipt.part_id] += receipt.open
    lines = [
        PartStockLine(
            part=part,
            total=sum(entry.quantity for entry in by_part[part_id]),
            incoming=incoming[part_id],
            locations=[
                LocatedParts(location=locations[entry.location_id], quantity=entry.quantity)
                for entry in by_part[part_id]
                if entry.location_id in locations
            ],
        )
        for part_id, part in parts.items()
    ]
    lines.sort(key=lambda line: line.part.part_number)
    return lines


async def receipt_views(uow: InventoryUnitOfWork, receipts: list[PartReceipt]) -> list[ReceiptView]:
    parts = await uow.manufacturing.parts({receipt.part_id for receipt in receipts})
    jobs = await uow.manufacturing.print_jobs({receipt.print_job_id for receipt in receipts})
    return [
        ReceiptView(
            receipt=receipt,
            part=parts.get(receipt.part_id),
            job=jobs.get(receipt.print_job_id),
        )
        for receipt in receipts
    ]


class PartStoreService:
    def __init__(self, *, uow_factory: UnitOfWorkFactory, clock: Clock) -> None:
        self._uow = uow_factory
        self._clock = clock

    async def receive_print_job(self, print_job_id: UUID) -> int:
        """The good parts of a finished plate arrive in receiving; how many arrived.

        Delivery is at least once: parts that already arrived do not arrive again.
        """
        try:
            return await self._receive(print_job_id)
        except UniqueViolationError:
            # Delivered twice at the same moment; the other delivery booked it.
            _logger.info("inventory.receive.duplicate", print_job=str(print_job_id))
            return 0

    async def _receive(self, print_job_id: UUID) -> int:
        async with self._uow() as uow:
            yielded = await uow.manufacturing.print_job_yield(print_job_id)
            if yielded is None:
                return 0
            arrived = {receipt.part_id for receipt in await uow.receipts.for_job(print_job_id)}
            now = self._clock.now()
            receipts = [
                PartReceipt.arrive(
                    print_job_id=print_job_id, part_id=part_id, quantity=good, now=now
                )
                for part_id, good in yielded.good.items()
                if part_id not in arrived
            ]
            if not receipts:
                return 0
            for receipt in receipts:
                uow.receipts.add(receipt)
            parts = sum(receipt.quantity for receipt in receipts)
            uow.publish(
                PartsArrived(
                    aggregate_id=print_job_id,
                    occurred_at=now,
                    number=yielded.job.number,
                    parts=parts,
                )
            )
            await uow.commit()
            return parts

    async def overview(self) -> list[PartStockLine]:
        """Every part that lies somewhere or waits in receiving, by part number."""
        async with self._uow() as uow:
            receipts = await uow.receipts.open()
            part_ids = set(await uow.part_stock.totals()) | {r.part_id for r in receipts}
            parts = await uow.manufacturing.parts(part_ids)
            return await stock_lines(uow, parts, receipts)

    async def receiving(self) -> list[ReceiptView]:
        """What waits in receiving, oldest first."""
        async with self._uow() as uow:
            return await receipt_views(uow, await uow.receipts.open())

    async def details(self, part_number: str) -> PartDetails:
        async with self._uow() as uow:
            part = await uow.manufacturing.part_by_number(part_number.strip().upper())
            if part is None:
                raise PartNotFoundError
            return await self._details(uow, part)

    async def _details(self, uow: InventoryUnitOfWork, part: PartInfo) -> PartDetails:
        receipts = await uow.receipts.open(part.part_id)
        (line,) = await stock_lines(uow, {part.part_id: part}, receipts)
        entries = await uow.part_ledger.for_part(part.part_id, limit=HISTORY_LIMIT)
        locations = await uow.locations.by_ids(
            {
                location_id
                for entry in entries
                for location_id in (entry.from_location_id, entry.to_location_id)
                if location_id is not None
            }
        )
        names = await uow.staff.names(
            {entry.staff_id for entry in entries if entry.staff_id is not None}
        )
        booked_receipts = await uow.receipts.by_ids(
            {entry.receipt_id for entry in entries if entry.receipt_id is not None}
        )
        jobs = await uow.manufacturing.print_jobs(
            {receipt.print_job_id for receipt in booked_receipts.values()}
        )
        units = {
            unit_id: await uow.units.get(unit_id)
            for unit_id in {entry.unit_id for entry in entries if entry.unit_id is not None}
        }
        history = []
        for entry in entries:
            receipt = booked_receipts.get(entry.receipt_id) if entry.receipt_id else None
            job = jobs.get(receipt.print_job_id) if receipt is not None else None
            unit = units.get(entry.unit_id) if entry.unit_id else None
            history.append(
                PartHistoryEntry(
                    entry=entry,
                    from_location=locations.get(entry.from_location_id)
                    if entry.from_location_id
                    else None,
                    to_location=locations.get(entry.to_location_id)
                    if entry.to_location_id
                    else None,
                    staff_name=names.get(entry.staff_id) if entry.staff_id else None,
                    job_number=job.number if job is not None else None,
                    unit_code=unit.code if unit is not None else None,
                )
            )
        return PartDetails(line=line, receipts=await receipt_views(uow, receipts), history=history)

    async def write_off(self, receipt_id: UUID, *, note: str, staff_id: UUID) -> ReceiptView:
        """The rest of a receipt never reached a shelf: it leaves receiving."""
        async with self._uow() as uow:
            receipt = await uow.receipts.get(receipt_id, for_update=True)
            if receipt is None:
                raise ReceiptNotFoundError
            now = self._clock.now()
            journal = PartJournal(uow, staff_id=staff_id, now=now)
            journal.book(receipt.write_off(note, now))
            await journal.announce()
            await uow.commit()
            (view,) = await receipt_views(uow, [receipt])
            return view

    async def count(
        self,
        part_number: str,
        *,
        location_code: str,
        quantity: int,
        note: str,
        staff_id: UUID,
    ) -> PartDetails:
        """Set the part's quantity in the location to what was counted there."""
        async with self._uow() as uow:
            part = await uow.manufacturing.part_by_number(part_number.strip().upper())
            if part is None:
                raise PartNotFoundError
            location = await resolve_location(uow, location_code, "location_code")
            now = self._clock.now()
            stock = await uow.part_stock.lock(part.part_id, location.id, now=now)
            movement = stock.count(quantity, note, now)
            if movement is not None:
                journal = PartJournal(uow, staff_id=staff_id, now=now)
                journal.book(movement)
                await journal.announce()
            await uow.commit()
            return await self._details(uow, part)
