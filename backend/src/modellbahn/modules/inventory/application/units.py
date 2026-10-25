"""Use cases of units: label new ones, look one up with its history, scrap, count the stock."""

from dataclasses import dataclass
from uuid import UUID

from modellbahn.modules.catalog.contracts.variants import SaleVariant
from modellbahn.modules.inventory.application.allocation import Allocator
from modellbahn.modules.inventory.application.common import Journal, UnitOfWorkFactory
from modellbahn.modules.inventory.application.ports import InventoryUnitOfWork
from modellbahn.modules.inventory.domain.codes import new_unit_code, normalize_unit_code
from modellbahn.modules.inventory.domain.errors import (
    InvalidFieldError,
    LocationNotFoundError,
    UnitNotFoundError,
    VariantNotFoundError,
)
from modellbahn.modules.inventory.domain.events import AllocationBackordered
from modellbahn.modules.inventory.domain.model import (
    UNITS_PER_BATCH_MAX,
    AllocationStatus,
    LedgerEntry,
    Location,
    Movement,
    Unit,
    UnitStatus,
)
from modellbahn.platform.clock import Clock


@dataclass(frozen=True, slots=True)
class UnitView:
    """A unit with what it is, where it lies and whom it is promised to."""

    unit: Unit
    variant: SaleVariant | None
    location: Location | None
    order_id: UUID | None
    order_number: str | None


@dataclass(frozen=True, slots=True)
class HistoryEntry:
    entry: LedgerEntry
    from_location: Location | None
    to_location: Location | None
    staff_name: str | None
    order_number: str | None


@dataclass(frozen=True, slots=True)
class UnitDetails:
    view: UnitView
    history: list[HistoryEntry]
    """Oldest first."""


@dataclass(frozen=True, slots=True)
class StockLine:
    """The units of one variant by state, and the pieces still waiting for one."""

    variant_id: UUID
    variant: SaleVariant | None
    labeled: int
    in_stock: int
    allocated: int
    picked: int
    backordered: int


async def unit_views(uow: InventoryUnitOfWork, units: list[Unit]) -> list[UnitView]:
    variants = await uow.catalog.variants({unit.variant_id for unit in units})
    locations = await uow.locations.by_ids(
        [unit.location_id for unit in units if unit.location_id is not None]
    )
    allocations = await uow.allocations.by_ids(
        [unit.allocation_id for unit in units if unit.allocation_id is not None]
    )
    numbers = await uow.orders.numbers({allocation.order_id for allocation in allocations.values()})
    views = []
    for unit in units:
        allocation = allocations.get(unit.allocation_id) if unit.allocation_id else None
        views.append(
            UnitView(
                unit=unit,
                variant=variants.get(unit.variant_id),
                location=locations.get(unit.location_id) if unit.location_id else None,
                order_id=allocation.order_id if allocation else None,
                order_number=numbers.get(allocation.order_id) if allocation else None,
            )
        )
    return views


class UnitService:
    def __init__(self, *, uow_factory: UnitOfWorkFactory, clock: Clock) -> None:
        self._uow = uow_factory
        self._clock = clock

    async def label_units(
        self,
        *,
        variant_id: UUID,
        quantity: int,
        location_code: str | None,
        staff_id: UUID | None,
    ) -> list[UnitView]:
        """New units of a variant, ready for their labels.

        With a location they are put away at once, and orders waiting for the variant
        get them first; without one they wait for the put-away scan.
        """
        if not 1 <= quantity <= UNITS_PER_BATCH_MAX:
            raise InvalidFieldError(
                "quantity", "out_of_range", f"between 1 and {UNITS_PER_BATCH_MAX}"
            )
        async with self._uow() as uow:
            if variant_id not in await uow.catalog.variants([variant_id]):
                raise VariantNotFoundError
            location = None
            if location_code is not None:
                location = await uow.locations.get_by_code(location_code.strip().upper())
                if location is None:
                    raise LocationNotFoundError
                if not location.holds_goods:
                    raise InvalidFieldError(
                        "location_code", "holds_no_goods", f"a {location.kind} holds no goods"
                    )
            now = self._clock.now()
            created: list[tuple[Unit, Movement]] = []
            for code in await _fresh_codes(uow, quantity):
                unit, labelled = Unit.label(variant_id=variant_id, code=code, now=now)
                uow.units.add(unit)
                created.append((unit, labelled))
            await uow.flush()
            journal = Journal(uow, staff_id=staff_id, now=now)
            allocator = Allocator(uow, journal)
            for unit, labelled in created:
                await journal.book(unit, labelled)
                if location is not None:
                    journal.know(location)
                    await journal.book(unit, unit.put_away(location, now))
                    await allocator.serve_backorder(unit)
            await uow.commit()
            return await unit_views(uow, [unit for unit, _ in created])

    async def details(self, code: str) -> UnitDetails:
        async with self._uow() as uow:
            unit = await uow.units.get_by_code(normalize_unit_code(code))
            if unit is None:
                raise UnitNotFoundError
            (view,) = await unit_views(uow, [unit])
            entries = await uow.ledger.for_unit(unit.id)
            location_ids = {
                location_id
                for entry in entries
                for location_id in (entry.from_location_id, entry.to_location_id)
                if location_id is not None
            }
            locations = await uow.locations.by_ids(location_ids)
            names = await uow.staff.names(
                {entry.staff_id for entry in entries if entry.staff_id is not None}
            )
            allocations = await uow.allocations.by_ids(
                {entry.allocation_id for entry in entries if entry.allocation_id is not None}
            )
            numbers = await uow.orders.numbers({a.order_id for a in allocations.values()})
        history = []
        for entry in entries:
            allocation = allocations.get(entry.allocation_id) if entry.allocation_id else None
            history.append(
                HistoryEntry(
                    entry=entry,
                    from_location=locations.get(entry.from_location_id)
                    if entry.from_location_id
                    else None,
                    to_location=locations.get(entry.to_location_id)
                    if entry.to_location_id
                    else None,
                    staff_name=names.get(entry.staff_id) if entry.staff_id else None,
                    order_number=numbers.get(allocation.order_id) if allocation else None,
                )
            )
        return UnitDetails(view=view, history=history)

    async def scrap(self, code: str, *, note: str, staff_id: UUID | None) -> UnitView:
        """Take a broken or lost unit out of the stock; an order it was promised to gets another."""
        async with self._uow() as uow:
            unit = await uow.units.get_by_code(normalize_unit_code(code), for_update=True)
            if unit is None:
                raise UnitNotFoundError
            now = self._clock.now()
            journal = Journal(uow, staff_id=staff_id, now=now)
            movement = unit.scrap(note, now)
            await journal.book(unit, movement)
            if movement.allocation_id is not None:
                allocation = await uow.allocations.get(movement.allocation_id)
                if allocation is not None and allocation.status is AllocationStatus.OPEN:
                    await uow.flush()
                    backordered = await Allocator(uow, journal).reserve([allocation])
                    uow.publish(
                        *(
                            AllocationBackordered(
                                aggregate_id=a.id,
                                occurred_at=now,
                                order_id=a.order_id,
                                variant_id=a.variant_id,
                            )
                            for a in backordered
                        )
                    )
            await uow.commit()
            (view,) = await unit_views(uow, [unit])
            return view

    async def stock(self) -> list[StockLine]:
        """Every variant that has units or backorders, by product name."""
        async with self._uow() as uow:
            counts = await uow.units.counts()
            backorders = await uow.allocations.backorder_counts()
            variant_ids = {count.variant_id for count in counts} | set(backorders)
            variants = await uow.catalog.variants(variant_ids)
        by_variant: dict[UUID, dict[UnitStatus, int]] = {}
        for count in counts:
            by_variant.setdefault(count.variant_id, {})[count.status] = count.count
        lines = [
            StockLine(
                variant_id=variant_id,
                variant=variants.get(variant_id),
                labeled=by_variant.get(variant_id, {}).get(UnitStatus.LABELED, 0),
                in_stock=by_variant.get(variant_id, {}).get(UnitStatus.IN_STOCK, 0),
                allocated=by_variant.get(variant_id, {}).get(UnitStatus.ALLOCATED, 0),
                picked=by_variant.get(variant_id, {}).get(UnitStatus.PICKED, 0),
                backordered=backorders.get(variant_id, 0),
            )
            for variant_id in variant_ids
        ]
        lines = [
            line
            for line in lines
            if line.labeled or line.in_stock or line.allocated or line.picked or line.backordered
        ]
        lines.sort(key=lambda line: (line.variant.title if line.variant else "", line.variant_id))
        return lines

    async def product_of(self, code: str) -> str | None:
        """The slug of the product a unit is a piece of, for a customer scanning its label."""
        async with self._uow() as uow:
            unit = await uow.units.get_by_code(normalize_unit_code(code))
            if unit is None:
                return None
            variant = (await uow.catalog.variants([unit.variant_id])).get(unit.variant_id)
        if variant is None or not variant.purchasable:
            return None
        return variant.product_slug


async def _fresh_codes(uow: InventoryUnitOfWork, quantity: int) -> list[str]:
    """``quantity`` new unit codes that no unit has yet (a clash is astronomically rare)."""
    codes: set[str] = set()
    while len(codes) < quantity:
        candidates = {new_unit_code() for _ in range(quantity - len(codes))}
        codes |= candidates - await uow.units.existing_codes(candidates)
    return sorted(codes)
