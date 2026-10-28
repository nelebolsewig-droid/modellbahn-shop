"""Who gets which unit: allocating paid orders, backorders, releasing, shipping, pick lists.

A paid order gets one allocation per piece. Each takes the oldest free unit of its
variant (first in, first out); a piece without a unit is backordered and gets the next
unit of its variant that is put away, before anybody else. A cancelled order gives its
units back; a shipped one takes them along.

The handlers run at least once: allocating checks whether the order already has its
allocations, releasing and shipping only touch what is still open.
"""

from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

import structlog

from modellbahn.modules.inventory.application.common import Journal, UnitOfWorkFactory
from modellbahn.modules.inventory.application.ports import InventoryUnitOfWork
from modellbahn.modules.inventory.domain.errors import (
    OrderNotAllocatableError,
    OrderNotFoundError,
)
from modellbahn.modules.inventory.domain.events import AllocationBackordered
from modellbahn.modules.inventory.domain.model import (
    Allocation,
    AllocationStatus,
    Location,
    Unit,
    UnitStatus,
)
from modellbahn.modules.sales.contracts.orders import OrderStatus, OrderSummary
from modellbahn.platform.clock import Clock
from modellbahn.platform.uow import UniqueViolationError

_logger = structlog.get_logger(__name__)


class Allocator:
    """The allocation rules, applied inside the caller's unit of work."""

    def __init__(self, uow: InventoryUnitOfWork, journal: Journal) -> None:
        self._uow = uow
        self._journal = journal

    async def serve_backorder(self, unit: Unit) -> Allocation | None:
        """Give a unit that just became free to the order waiting longest for its variant."""
        if not unit.is_free:
            return None
        allocation = await self._uow.allocations.oldest_backorder(unit.variant_id)
        if allocation is None:
            return None
        self._journal.know(allocation)
        await self._journal.book(unit, unit.allocate(allocation.id, self._journal.now))
        return allocation

    async def reserve(self, allocations: list[Allocation]) -> list[Allocation]:
        """Give each allocation the oldest free unit of its variant; the backordered rest."""
        backordered: list[Allocation] = []
        by_variant: dict[UUID, list[Allocation]] = {}
        for allocation in allocations:
            by_variant.setdefault(allocation.variant_id, []).append(allocation)
        for variant_id, wanting in by_variant.items():
            free = await self._uow.units.oldest_free(variant_id, limit=len(wanting))
            for allocation, unit in zip(wanting, free, strict=False):
                self._journal.know(allocation)
                await self._journal.book(unit, unit.allocate(allocation.id, self._journal.now))
            backordered.extend(wanting[len(free) :])
        return backordered


class PieceState(StrEnum):
    """How far one piece of an order has come."""

    BACKORDERED = "backordered"
    RESERVED = "reserved"
    PICKED = "picked"
    SHIPPED = "shipped"
    RELEASED = "released"


@dataclass(frozen=True, slots=True)
class PickItem:
    allocation_id: UUID
    order_line_id: UUID
    position: int
    piece: int
    variant_id: UUID
    sku: str
    title: str
    state: PieceState
    unit_code: str | None
    location: Location | None


@dataclass(frozen=True, slots=True)
class PickList:
    """An order's pieces in walking order: by location, backorders last, picked at the end."""

    order: OrderSummary
    items: list[PickItem]

    @property
    def total(self) -> int:
        return sum(1 for item in self.items if item.state is not PieceState.RELEASED)

    @property
    def picked(self) -> int:
        return sum(
            1 for item in self.items if item.state in {PieceState.PICKED, PieceState.SHIPPED}
        )

    @property
    def is_complete(self) -> bool:
        return self.total > 0 and self.picked == self.total

    @property
    def is_allocated(self) -> bool:
        return bool(self.items)

    def next_expected(self) -> PickItem | None:
        """The piece to fetch next: the first reserved one on the walk."""
        return next((item for item in self.items if item.state is PieceState.RESERVED), None)


_WALK_ORDER = {
    PieceState.RESERVED: 0,
    PieceState.BACKORDERED: 1,
    PieceState.PICKED: 2,
    PieceState.SHIPPED: 3,
    PieceState.RELEASED: 4,
}


def piece_state(allocation: Allocation, unit: Unit | None) -> PieceState:
    if allocation.status is AllocationStatus.RELEASED:
        return PieceState.RELEASED
    if allocation.status is AllocationStatus.SHIPPED:
        return PieceState.SHIPPED
    if unit is None:
        return PieceState.BACKORDERED
    return PieceState.PICKED if unit.status is UnitStatus.PICKED else PieceState.RESERVED


async def load_pick_list(uow: InventoryUnitOfWork, order: OrderSummary) -> PickList:
    allocations = await uow.allocations.for_order(order.id)
    units = await uow.units.serving([allocation.id for allocation in allocations])
    locations = await uow.locations.by_ids(
        [unit.location_id for unit in units.values() if unit.location_id is not None]
    )
    lines = {line.id: line for line in order.lines}
    items: list[PickItem] = []
    for allocation in allocations:
        line = lines.get(allocation.order_line_id)
        unit = units.get(allocation.id)
        location = locations.get(unit.location_id) if unit and unit.location_id else None
        items.append(
            PickItem(
                allocation_id=allocation.id,
                order_line_id=allocation.order_line_id,
                position=line.position if line else 0,
                piece=allocation.piece,
                variant_id=allocation.variant_id,
                sku=line.sku if line else "",
                title=line.title if line else "",
                state=piece_state(allocation, unit),
                unit_code=unit.code if unit else None,
                location=location,
            )
        )
    items.sort(
        key=lambda item: (
            _WALK_ORDER[item.state],
            item.location.path if item.location else "",
            item.position,
            item.piece,
        )
    )
    return PickList(order=order, items=items)


class AllocationService:
    def __init__(self, *, uow_factory: UnitOfWorkFactory, clock: Clock) -> None:
        self._uow = uow_factory
        self._clock = clock

    async def allocate_order(self, order_id: UUID, *, staff_id: UUID | None = None) -> PickList:
        """Allocate a paid order (once; again it changes nothing) and return its pick list.

        Raises :class:`OrderNotAllocatableError` for an order that is not paid.
        """
        try:
            return await self._allocate(order_id, staff_id)
        except UniqueViolationError:
            # Allocated at the same moment by somebody else (the handler and a click).
            return await self.pick_list(order_id)

    async def _allocate(self, order_id: UUID, staff_id: UUID | None) -> PickList:
        async with self._uow() as uow:
            order = await uow.orders.summary(order_id)
            if order is None:
                raise OrderNotFoundError
            if await uow.allocations.for_order(order_id):
                return await load_pick_list(uow, order)
            if order.status is not OrderStatus.PAID:
                raise OrderNotAllocatableError
            now = self._clock.now()
            allocations = [
                Allocation.open(
                    order_id=order.id,
                    order_line_id=line.id,
                    variant_id=line.variant_id,
                    piece=piece,
                    now=now,
                )
                for line in order.lines
                for piece in range(line.quantity)
            ]
            for allocation in allocations:
                uow.allocations.add(allocation)
            await uow.flush()
            journal = Journal(uow, staff_id=staff_id, now=now)
            backordered = await Allocator(uow, journal).reserve(allocations)
            uow.publish(
                *(
                    AllocationBackordered(
                        aggregate_id=allocation.id,
                        occurred_at=now,
                        order_id=order.id,
                        variant_id=allocation.variant_id,
                    )
                    for allocation in backordered
                )
            )
            await uow.commit()
            _logger.info(
                "inventory.order.allocated",
                order=order.number,
                pieces=len(allocations),
                backordered=len(backordered),
            )
            return await load_pick_list(uow, order)

    async def release_order(self, order_id: UUID) -> None:
        """The order was cancelled: its units go back, its backorders lapse."""
        async with self._uow() as uow:
            allocations = await uow.allocations.for_order(order_id, for_update=True)
            open_ones = [a for a in allocations if a.status is AllocationStatus.OPEN]
            if not open_ones:
                return
            now = self._clock.now()
            journal = Journal(uow, staff_id=None, now=now)
            allocator = Allocator(uow, journal)
            units = await uow.units.serving([a.id for a in open_ones], for_update=True)
            freed: list[Unit] = []
            for allocation in open_ones:
                journal.know(allocation)
                unit = units.get(allocation.id)
                if unit is not None:
                    await journal.book(unit, unit.release(now))
                    freed.append(unit)
                allocation.release(now)
            # Released first, then handed on: another order may be waiting for them.
            await uow.flush()
            for unit in freed:
                await allocator.serve_backorder(unit)
            await uow.commit()
            _logger.info("inventory.order.released", order_id=str(order_id), units=len(freed))

    async def ship_order(self, order_id: UUID) -> None:
        """The parcel left: its picked units are shipped, the allocations done."""
        async with self._uow() as uow:
            allocations = await uow.allocations.for_order(order_id, for_update=True)
            open_ones = [a for a in allocations if a.status is AllocationStatus.OPEN]
            if not open_ones:
                return
            now = self._clock.now()
            journal = Journal(uow, staff_id=None, now=now)
            units = await uow.units.serving([a.id for a in open_ones], for_update=True)
            for allocation in open_ones:
                journal.know(allocation)
                unit = units.get(allocation.id)
                if unit is None or unit.status is not UnitStatus.PICKED:
                    # Sales ships only completely picked orders; this would be a bug.
                    _logger.warning(
                        "inventory.ship.unpicked_piece",
                        order_id=str(order_id),
                        allocation_id=str(allocation.id),
                    )
                    continue
                await journal.book(unit, unit.ship(now))
                allocation.ship(now)
            await uow.commit()

    async def pick_list(self, order_id: UUID) -> PickList:
        async with self._uow() as uow:
            order = await uow.orders.summary(order_id)
            if order is None:
                raise OrderNotFoundError
            return await load_pick_list(uow, order)
