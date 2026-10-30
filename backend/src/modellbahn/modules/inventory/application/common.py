"""What the inventory use cases share: the unit of work factory and the journal keepers."""

from collections.abc import Callable
from datetime import datetime
from uuid import UUID

from modellbahn.modules.inventory.application.ports import InventoryUnitOfWork
from modellbahn.modules.inventory.domain.errors import InvalidFieldError, LocationNotFoundError
from modellbahn.modules.inventory.domain.events import PartStockChanged, StockChanged
from modellbahn.modules.inventory.domain.model import (
    Allocation,
    LedgerEntry,
    Location,
    Movement,
    Unit,
)
from modellbahn.modules.inventory.domain.parts import (
    PartLedgerEntry,
    PartMovement,
    PartMovementReason,
)

type UnitOfWorkFactory = Callable[[], InventoryUnitOfWork]


async def resolve_location(uow: InventoryUnitOfWork, code: str, field: str) -> Location:
    """The location with ``code`` that can hold goods; ``field`` names the input."""
    location = await uow.locations.get_by_code(code.strip().upper())
    if location is None:
        raise LocationNotFoundError
    if not location.holds_goods:
        raise InvalidFieldError(field, "holds_no_goods", f"a {location.kind} holds no goods")
    return location


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


type _Way = tuple[UUID, PartMovementReason, UUID | None, UUID | None]


class PartJournal:
    """Books part movements inside one unit of work; :meth:`announce` tells the screens.

    An assembly takes parts for every kit from every box, so the live events are summed
    per part, reason and way: one event says "12 Schornsteine out of R02-F04-B12".
    Entries refer to receipts, units and scans by foreign key; callers flush new rows of
    those first.
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
        self._ways: dict[_Way, int] = {}
        self.booked: list[PartLedgerEntry] = []

    def book(
        self, movement: PartMovement, *, reverses: PartLedgerEntry | None = None
    ) -> PartLedgerEntry:
        entry = PartLedgerEntry.book(
            movement,
            scan_id=self._scan_id,
            staff_id=self._staff_id,
            now=self._now,
            reverses_id=reverses.id if reverses is not None else None,
        )
        self._uow.part_ledger.add(entry)
        self.booked.append(entry)
        way = (
            movement.part_id,
            movement.reason,
            movement.from_location_id,
            movement.to_location_id,
        )
        self._ways[way] = self._ways.get(way, 0) + movement.quantity
        return entry

    async def announce(self) -> None:
        """Publish what was booked since the last call, one event per part and way."""
        if not self._ways:
            return
        parts = await self._uow.manufacturing.parts({way[0] for way in self._ways})
        locations = await self._uow.locations.by_ids(
            {place for way in self._ways for place in way[2:] if place is not None}
        )

        def code(location_id: UUID | None) -> str | None:
            location = locations.get(location_id) if location_id is not None else None
            return location.code if location is not None else None

        for (part_id, reason, source, target), quantity in self._ways.items():
            part = parts.get(part_id)
            self._uow.publish(
                PartStockChanged(
                    aggregate_id=part_id,
                    occurred_at=self._now,
                    part_number=part.part_number if part is not None else "",
                    reason=reason.value,
                    quantity=quantity,
                    location_code=code(target),
                    previous_location_code=code(source),
                )
            )
        self._ways.clear()
