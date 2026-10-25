"""What the inventory use cases share: the unit of work factory and the journal keeper."""

from collections.abc import Callable
from datetime import datetime
from uuid import UUID

from modellbahn.modules.inventory.application.ports import InventoryUnitOfWork
from modellbahn.modules.inventory.domain.events import StockChanged
from modellbahn.modules.inventory.domain.model import (
    Allocation,
    LedgerEntry,
    Location,
    Movement,
    Unit,
)

type UnitOfWorkFactory = Callable[[], InventoryUnitOfWork]


class Journal:
    """Books movements inside one unit of work: a journal entry and a live event each.

    Entries refer to their unit, scan and allocation by foreign key. SQLAlchemy orders
    the inserts of unrelated classes as it likes, so callers flush new rows of those
    before they book movements that refer to them.
    """

    def __init__(
        self,
        uow: InventoryUnitOfWork,
        *,
        staff_id: UUID | None,
        now: datetime,
        scan_id: UUID | None = None,
    ) -> None:
        self._uow = uow
        self._staff_id = staff_id
        self._scan_id = scan_id
        self._now = now
        self._locations: dict[UUID, Location] = {}
        self._allocations: dict[UUID, Allocation] = {}
        self.booked: list[LedgerEntry] = []

    @property
    def now(self) -> datetime:
        return self._now

    def know(self, *items: Location | Allocation) -> None:
        """Remember locations and allocations at hand, so booking needs no lookup."""
        for item in items:
            if isinstance(item, Location):
                self._locations[item.id] = item
            else:
                self._allocations[item.id] = item

    async def book(
        self, unit: Unit, movement: Movement, *, reverses: LedgerEntry | None = None
    ) -> LedgerEntry:
        entry = LedgerEntry.book(
            movement,
            scan_id=self._scan_id,
            staff_id=self._staff_id,
            now=self._now,
            reverses_id=reverses.id if reverses is not None else None,
        )
        self._uow.ledger.add(entry)
        self.booked.append(entry)
        allocation = await self._allocation(movement.allocation_id)
        self._uow.publish(
            StockChanged(
                aggregate_id=unit.id,
                occurred_at=self._now,
                unit_code=unit.code,
                variant_id=unit.variant_id,
                reason=movement.reason.value,
                status=unit.status.value,
                location_code=await self._code(movement.to_location_id),
                previous_location_code=await self._code(movement.from_location_id),
                order_id=allocation.order_id if allocation is not None else None,
            )
        )
        return entry

    async def _code(self, location_id: UUID | None) -> str | None:
        if location_id is None:
            return None
        location = self._locations.get(location_id)
        if location is None:
            location = await self._uow.locations.get(location_id)
            if location is None:  # pragma: no cover - locations with history are never deleted
                return None
            self._locations[location_id] = location
        return location.code

    async def _allocation(self, allocation_id: UUID | None) -> Allocation | None:
        if allocation_id is None:
            return None
        allocation = self._allocations.get(allocation_id)
        if allocation is None:
            allocation = await self._uow.allocations.get(allocation_id)
            if allocation is not None:
                self._allocations[allocation_id] = allocation
        return allocation
