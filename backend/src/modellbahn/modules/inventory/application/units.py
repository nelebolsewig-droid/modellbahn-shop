"""Use cases of units: label, list, move, look one up with its history, scrap, count,
book in again, correct the variant, and take stock of a location."""

from collections.abc import Collection, Sequence
from dataclasses import dataclass
from typing import Final
from uuid import UUID

from modellbahn.modules.catalog.contracts.variants import SaleVariant
from modellbahn.modules.inventory.application.allocation import Allocator
from modellbahn.modules.inventory.application.common import (
    Journal,
    UnitOfWorkFactory,
    resolve_location,
)
from modellbahn.modules.inventory.application.ports import InventoryUnitOfWork
from modellbahn.modules.inventory.domain.codes import new_unit_code, normalize_unit_code
from modellbahn.modules.inventory.domain.errors import (
    InvalidFieldError,
    UnitNotFoundError,
    VariantNotFoundError,
)
from modellbahn.modules.inventory.domain.events import AllocationBackordered
from modellbahn.modules.inventory.domain.model import (
    UNITS_COUNTED_MAX,
    UNITS_PER_BATCH_MAX,
    UNITS_SELECTED_MAX,
    Allocation,
    AllocationStatus,
    LedgerEntry,
    Location,
    Movement,
    MovementReason,
    ScrapReason,
    Unit,
    UnitStatus,
    take_stock,
    units_to_move,
    units_to_restore,
    units_to_scrap,
)
from modellbahn.modules.manufacturing.contracts.parts import PartInfo
from modellbahn.platform.clock import Clock

# What one list shows is what one batch may take: "select all" must always be sendable.
UNITS_LISTED_MAX: Final = UNITS_SELECTED_MAX


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
    from_variant: SaleVariant | None = None
    """Of a correction: what the unit was recorded as (the variant of the entry before)."""
    to_variant: SaleVariant | None = None
    """Of a correction: what the unit is."""


@dataclass(frozen=True, slots=True)
class AssembledPart:
    """Parts that went into the unit, and the box they came from."""

    part: PartInfo | None
    quantity: int
    location: Location | None


@dataclass(frozen=True, slots=True)
class UnitDetails:
    view: UnitView
    history: list[HistoryEntry]
    """Oldest first."""
    parts: list[AssembledPart]
    """What the unit was assembled from (empty for a unit labelled by hand)."""


@dataclass(frozen=True, slots=True)
class UnitMove:
    """What moving several units into one location did."""

    location: Location
    moved: int
    """Units that went there: labelled ones stored, stored ones moved."""
    already_there: int
    """Units that lay there already and were left alone."""
    reserved: int
    """Of the moved ones, those that went straight to a waiting order."""


@dataclass(frozen=True, slots=True)
class UnitScrap:
    """What taking several units out of the stock did."""

    scrapped: int
    already_scrapped: int
    """Units that were out already and were left alone."""


@dataclass(frozen=True, slots=True)
class UnitRestore:
    """What booking several scrapped units in again did."""

    location: Location
    restored: int
    already_there: int
    """Units that lay there already (booked in by an earlier request) and were left alone."""
    reserved: int
    """Of the restored ones, those that went straight to a waiting order."""


@dataclass(frozen=True, slots=True)
class StocktakeResult:
    """What booking the count of one location did."""

    location: Location
    confirmed: int
    """Units found where the journal has them."""
    scrapped: int
    """Missing units that left the stock now."""
    found: int
    """Units put away here now: from elsewhere, unbooked, or booked in again."""
    reserved: int
    """Of the found ones, those that went straight to a waiting order."""


@dataclass(frozen=True, slots=True)
class UnitList:
    views: list[UnitView]
    """Oldest first."""
    more: bool
    """True if there are more than :data:`UNITS_LISTED_MAX`; the oldest are listed."""


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
            location = (
                await resolve_location(uow, location_code, "location_code")
                if location_code is not None
                else None
            )
            now = self._clock.now()
            journal = Journal(uow, staff_id=staff_id, now=now)
            units = await label_new_units(
                uow, journal, variant_id=variant_id, quantity=quantity, location=location
            )
            await uow.commit()
            return await unit_views(uow, units)

    async def list_units(
        self, variant_id: UUID | None, *, statuses: Collection[UnitStatus] | None = None
    ) -> UnitList:
        """Pieces, oldest first: of one article, in some states (``None``: any), or both.

        Every unlabelled piece of every article (``statuses={LABELED}``) is the list of
        what still has to be put away before the shop can sell it.
        """
        async with self._uow() as uow:
            units = await uow.units.listed(
                variant_id=variant_id, statuses=statuses, limit=UNITS_LISTED_MAX + 1
            )
            views = await unit_views(uow, units[:UNITS_LISTED_MAX])
        return UnitList(views=views, more=len(units) > UNITS_LISTED_MAX)

    async def move_units(
        self, unit_ids: Sequence[UUID], *, location_code: str, staff_id: UUID | None
    ) -> UnitMove:
        """Put several units into one location in one go, without the scanner (*Umlagern*).

        All or nothing, booked like the put-away scan: labelled units are stored, stored
        ones move, reserved ones keep their order, and a unit that becomes free goes to
        the order waiting longest for it. Units already there stay untouched, so sending
        the same request again is harmless. A unit that is picked, shipped, scrapped or
        unknown refuses the whole request (:class:`UnitsNotMovableError`).
        """
        wanted = list(dict.fromkeys(unit_ids))
        if not 1 <= len(wanted) <= UNITS_SELECTED_MAX:
            raise InvalidFieldError(
                "unit_ids", "out_of_range", f"between 1 and {UNITS_SELECTED_MAX} units"
            )
        async with self._uow() as uow:
            location = await resolve_location(uow, location_code, "location_code")
            units = await uow.units.lock(wanted)
            missing = set(wanted) - {unit.id for unit in units}
            moving = units_to_move(units, location, missing=missing)
            journal = Journal(uow, staff_id=staff_id, now=self._clock.now())
            reserved = 0
            for unit in moving:
                _, allocation = await put_away(uow, journal, unit, location)
                reserved += allocation is not None
            await uow.commit()
        return UnitMove(
            location=location,
            moved=len(moving),
            already_there=len(units) - len(moving),
            reserved=reserved,
        )

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
            corrections = _corrections(entries)
            variants = await uow.catalog.variants(
                {variant_id for pair in corrections.values() for variant_id in pair}
            )
            taken = await uow.part_ledger.for_unit(unit.id)
            part_infos = await uow.manufacturing.parts({entry.part_id for entry in taken})
            locations |= await uow.locations.by_ids(
                {entry.from_location_id for entry in taken if entry.from_location_id}
            )
        parts = [
            AssembledPart(
                part=part_infos.get(entry.part_id),
                quantity=entry.quantity,
                location=locations.get(entry.from_location_id) if entry.from_location_id else None,
            )
            for entry in taken
        ]
        history = []
        for index, entry in enumerate(entries):
            allocation = allocations.get(entry.allocation_id) if entry.allocation_id else None
            before, after = corrections.get(index, (None, None))
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
                    from_variant=variants.get(before) if before else None,
                    to_variant=variants.get(after) if after else None,
                )
            )
        return UnitDetails(view=view, history=history, parts=parts)

    async def scrap(
        self,
        code: str,
        *,
        note: str,
        staff_id: UUID | None,
        reason: ScrapReason | None = None,
    ) -> UnitView:
        """Take a unit out of the stock (sold elsewhere, broken, lost); an order it was
        promised to, even one being packed, gets another or waits for the workshop."""
        async with self._uow() as uow:
            unit = await uow.units.get_by_code(normalize_unit_code(code), for_update=True)
            if unit is None:
                raise UnitNotFoundError
            journal = Journal(uow, staff_id=staff_id, now=self._clock.now())
            movement = unit.scrap(note, journal.now, reason)
            await journal.book(unit, movement)
            await _allocate_again(uow, journal, [movement.allocation_id])
            await uow.commit()
            (view,) = await unit_views(uow, [unit])
            return view

    async def scrap_units(
        self,
        unit_ids: Sequence[UUID],
        *,
        reason: ScrapReason,
        note: str,
        staff_id: UUID | None,
    ) -> UnitScrap:
        """Take several units out of the stock in one go, all or nothing (*Ausbuchen*).

        Booked like scrapping one: a reserved unit's order gets another or waits for the
        workshop. Units picked or shipped for an order refuse the whole request
        (:class:`UnitsNotScrappableError`); units already out are left alone, so sending
        the same request again is harmless.
        """
        wanted = list(dict.fromkeys(unit_ids))
        if not 1 <= len(wanted) <= UNITS_SELECTED_MAX:
            raise InvalidFieldError(
                "unit_ids", "out_of_range", f"between 1 and {UNITS_SELECTED_MAX} units"
            )
        async with self._uow() as uow:
            units = await uow.units.lock(wanted)
            missing = set(wanted) - {unit.id for unit in units}
            leaving = units_to_scrap(units, missing=missing)
            journal = Journal(uow, staff_id=staff_id, now=self._clock.now())
            freed: list[UUID | None] = []
            for unit in leaving:
                movement = unit.scrap(note, journal.now, reason)
                await journal.book(unit, movement)
                freed.append(movement.allocation_id)
            # Only now: none of the units leaving may stand in for another one.
            await _allocate_again(uow, journal, freed)
            await uow.commit()
        return UnitScrap(scrapped=len(leaving), already_scrapped=len(units) - len(leaving))

    async def restore_units(
        self, unit_ids: Sequence[UUID], *, location_code: str, staff_id: UUID | None
    ) -> UnitRestore:
        """Book scrapped units in again into one location, all or nothing (*Wieder
        einbuchen*): scrapped by mistake, or turned up after all.

        They are free stock there without the reason and note of the scrap, and each goes
        to the order waiting longest for its variant, as a piece put away does. Units lying
        there already are left alone, so sending the same request again is harmless; a
        unit that is not scrapped refuses the request (:class:`UnitsNotRestorableError`).
        """
        wanted = list(dict.fromkeys(unit_ids))
        if not 1 <= len(wanted) <= UNITS_SELECTED_MAX:
            raise InvalidFieldError(
                "unit_ids", "out_of_range", f"between 1 and {UNITS_SELECTED_MAX} units"
            )
        async with self._uow() as uow:
            location = await resolve_location(uow, location_code, "location_code")
            units = await uow.units.lock(wanted)
            missing = set(wanted) - {unit.id for unit in units}
            returning = units_to_restore(units, location, missing=missing)
            journal = Journal(uow, staff_id=staff_id, now=self._clock.now())
            reserved = 0
            for unit in returning:
                reserved += await book_in_again(uow, journal, unit, location) is not None
            await uow.commit()
        return UnitRestore(
            location=location,
            restored=len(returning),
            already_there=len(units) - len(returning),
            reserved=reserved,
        )

    async def correct(self, code: str, *, variant_id: UUID, staff_id: UUID | None) -> UnitView:
        """The unit is another variant than its label says (*Ausführung ändern*).

        Only a labelled or free unit that no order ever had (never picked or shipped) may
        change (:class:`UnitNotCorrectableError`). It stays where it lies; a free one goes
        to an order waiting for its new variant. The journal entry carries the new
        variant; the entry before it the old one. Its label must be printed again.
        """
        async with self._uow() as uow:
            unit = await uow.units.get_by_code(normalize_unit_code(code), for_update=True)
            if unit is None:
                raise UnitNotFoundError
            if variant_id not in await uow.catalog.variants([variant_id]):
                raise VariantNotFoundError
            history = [entry.reason for entry in await uow.ledger.for_unit(unit.id)]
            journal = Journal(uow, staff_id=staff_id, now=self._clock.now())
            await journal.book(unit, unit.correct(variant_id, journal.now, history=history))
            await Allocator(uow, journal).serve_backorder(unit)
            await uow.commit()
            (view,) = await unit_views(uow, [unit])
            return view

    async def take_stock(
        self,
        location_code: str,
        *,
        present: Collection[UUID],
        missing: Collection[UUID],
        found: Collection[UUID],
        staff_id: UUID | None,
    ) -> StocktakeResult:
        """Book the count of one location in one go, all or nothing (*Inventur*).

        Missing units leave the stock as missing (an order they were reserved for gets
        another unit or waits for the workshop); found ones are put away here like any
        moved unit, scrapped ones booked in again. A count of a location that changed
        meanwhile is refused (:class:`StocktakeOutdatedError`), so no unit put there
        during the count is taken for missing. A repeated request books nothing twice.
        """
        named = set(present) | set(missing) | set(found)
        if len(named) > UNITS_COUNTED_MAX:
            raise InvalidFieldError(
                "unit_ids", "out_of_range", f"at most {UNITS_COUNTED_MAX} units"
            )
        async with self._uow() as uow:
            location = await resolve_location(uow, location_code, "code")
            lying = await uow.units.in_locations([location.id])
            units = await uow.units.lock(named | {unit.id for unit in lying})
            locked = {unit.id for unit in units}
            # Put there between the first look and the locks: the count cannot name them.
            arrived = [
                unit
                for unit in await uow.units.in_locations([location.id])
                if unit.id not in locked
            ]
            count = take_stock(
                location, [*units, *arrived], present=present, missing=missing, found=found
            )
            journal = Journal(uow, staff_id=staff_id, now=self._clock.now())
            reserved = 0
            for unit in count.found:
                if unit.status is UnitStatus.SCRAPPED:
                    allocation = await book_in_again(uow, journal, unit, location)
                else:
                    _, allocation = await put_away(uow, journal, unit, location)
                reserved += allocation is not None
            freed: list[UUID | None] = []
            for unit in count.missing:
                movement = unit.scrap(f"Inventur {location.code}", journal.now, ScrapReason.MISSING)
                await journal.book(unit, movement)
                freed.append(movement.allocation_id)
            # Only now: none of the missing units may stand in for another one.
            await _allocate_again(uow, journal, freed)
            await uow.commit()
        return StocktakeResult(
            location=location,
            confirmed=len(count.confirmed),
            scrapped=len(count.missing),
            found=len(count.found),
            reserved=reserved,
        )

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


async def label_new_units(
    uow: InventoryUnitOfWork,
    journal: Journal,
    *,
    variant_id: UUID,
    quantity: int,
    location: Location | None,
) -> list[Unit]:
    """New units of a variant, labelled, and put away into ``location`` if there is one.

    Put away at once, they serve orders waiting for the variant first. The units are
    flushed, so journal entries of the caller may refer to them.
    """
    now = journal.now
    created: list[tuple[Unit, Movement]] = []
    for code in await _fresh_codes(uow, quantity):
        unit, labelled = Unit.label(variant_id=variant_id, code=code, now=now)
        uow.units.add(unit)
        created.append((unit, labelled))
    await uow.flush()
    for unit, labelled in created:
        await journal.book(unit, labelled)
        if location is not None:
            await put_away(uow, journal, unit, location)
    return [unit for unit, _ in created]


async def _allocate_again(
    uow: InventoryUnitOfWork, journal: Journal, allocation_ids: Collection[UUID | None]
) -> None:
    """Pieces of orders whose unit left the stock get another one, or wait for the workshop."""
    found = await uow.allocations.by_ids({a for a in allocation_ids if a is not None})
    open_ = sorted(
        (a for a in found.values() if a.status is AllocationStatus.OPEN),
        key=lambda allocation: (allocation.created_at, allocation.id),
    )
    if not open_:
        return
    # The scrapped units must no longer count as free when the allocator looks.
    await uow.flush()
    backordered = await Allocator(uow, journal).reserve(open_)
    uow.publish(
        *(
            AllocationBackordered(
                aggregate_id=allocation.id,
                occurred_at=journal.now,
                order_id=allocation.order_id,
                variant_id=allocation.variant_id,
            )
            for allocation in backordered
        )
    )


async def put_away(
    uow: InventoryUnitOfWork, journal: Journal, unit: Unit, location: Location
) -> tuple[Movement, Allocation | None]:
    """Store or move ``unit`` into ``location`` and book it, as every way of putting away does.

    A unit that is free afterwards goes to the order waiting longest for its variant;
    that order's allocation is returned with the movement.
    """
    journal.know(location)
    movement = unit.put_away(location, journal.now)
    await journal.book(unit, movement)
    allocation = await Allocator(uow, journal).serve_backorder(unit)
    return movement, allocation


async def book_in_again(
    uow: InventoryUnitOfWork, journal: Journal, unit: Unit, location: Location
) -> Allocation | None:
    """Book a scrapped ``unit`` in again into ``location``; like a unit put away, it goes
    to the order waiting longest for its variant, whose allocation is returned."""
    journal.know(location)
    await journal.book(unit, unit.restore(location, journal.now))
    return await Allocator(uow, journal).serve_backorder(unit)


def _corrections(entries: Sequence[LedgerEntry]) -> dict[int, tuple[UUID, UUID]]:
    """The corrections in a unit's history by position: the variant before and after.

    The journal keeps the variant of the unit with every entry, so the variant before a
    correction is the one of the entry preceding it.
    """
    corrections: dict[int, tuple[UUID, UUID]] = {}
    for index, entry in enumerate(entries):
        if entry.reason is MovementReason.CORRECT and index > 0:
            corrections[index] = (entries[index - 1].variant_id, entry.variant_id)
    return corrections


async def _fresh_codes(uow: InventoryUnitOfWork, quantity: int) -> list[str]:
    """``quantity`` new unit codes that no unit has yet (a clash is astronomically rare)."""
    codes: set[str] = set()
    while len(codes) < quantity:
        candidates = {new_unit_code() for _ in range(quantity - len(codes))}
        codes |= candidates - await uow.units.existing_codes(candidates)
    return sorted(codes)
