"""Stock by quantity: how many pieces of each model lie where, and booking them by number.

A label names a model, not a piece (ADR 0027), so the Stellwerk works with numbers per
variant and place (ADR 0028): move three from one place to another, take two out, set a
place to what was counted. Which units that are, the system decides, oldest first; every
booking is one transaction that locks its units by id, books a journal entry and a live
event per unit, and serves waiting orders where pieces are added, as the scanner does.
"""

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Final
from uuid import UUID

from modellbahn.modules.catalog.contracts.variants import SaleVariant
from modellbahn.modules.inventory.application.common import (
    Journal,
    UnitOfWorkFactory,
    lock_oldest,
    place_name,
    resolve_location,
)
from modellbahn.modules.inventory.application.ports import InventoryUnitOfWork
from modellbahn.modules.inventory.application.units import label_new_units, put_away
from modellbahn.modules.inventory.domain.errors import (
    CountOutdatedError,
    CountTakesReservedError,
    InvalidFieldError,
    NotEnoughFreeError,
    NotEnoughPiecesError,
    ProductNotFoundError,
    VariantNotFoundError,
)
from modellbahn.modules.inventory.domain.model import (
    ON_SHELF,
    UNITS_PER_BATCH_MAX,
    Location,
    MovementReason,
    ScrapReason,
    Unit,
    UnitStatus,
)
from modellbahn.modules.sales.contracts.orders import OrderStatus
from modellbahn.platform.clock import Clock

STOCK_QUANTITY_MAX: Final = UNITS_PER_BATCH_MAX
"""Pieces one booking moves, takes out or adds per line."""
COUNT_LINES_MAX: Final = 200
HISTORY_ENTRIES: Final = 400
"""Journal entries read for a model's history; grouped, they make far fewer rows."""


@dataclass(frozen=True, slots=True)
class PlaceStock:
    """Pieces of one variant lying in one place."""

    location: Location
    place: str
    """``Regal 2, Boden 3``: how people call it (:func:`place_name`)."""
    variant_id: UUID
    variant: SaleVariant | None
    free: int
    reserved: int


@dataclass(frozen=True, slots=True)
class PlaceTotal:
    location: Location
    place: str
    quantity: int


@dataclass(frozen=True, slots=True)
class ProductStock:
    """A model's pieces over all its variants: for the list of models."""

    product_id: UUID
    free: int
    reserved: int
    labeled: int
    """Labelled long ago and never put away (the old way, before ADR 0027)."""
    backordered: int
    places: list[PlaceTotal]
    """Where its pieces lie, most first."""


@dataclass(frozen=True, slots=True)
class CountLine:
    variant_id: UUID
    location_code: str
    expected: int
    """What the Stellwerk showed there when counting began."""
    counted: int


@dataclass(frozen=True, slots=True)
class CountResult:
    missing: int
    """Pieces taken out as missing."""
    added: int
    """New pieces booked in where more lay than the Stellwerk knew."""
    reserved: int
    """Of the added ones, those that went straight to a waiting order."""


@dataclass(frozen=True, slots=True)
class MoveResult:
    moved: int
    source: Location
    target: Location


@dataclass(frozen=True, slots=True)
class ScrapResult:
    scrapped: int
    sources: list[PlaceTotal]


@dataclass(frozen=True, slots=True)
class HistoryRow:
    """One booking of a model: entries of one moment, person, kind and way, together."""

    occurred_at: datetime
    staff_name: str | None
    reason: MovementReason
    variant_id: UUID
    variant: SaleVariant | None
    quantity: int
    from_location: Location | None
    from_place: str | None
    to_location: Location | None
    to_place: str | None
    scan: bool
    """Booked by the scanner."""


def _check_quantity(quantity: int, field: str = "quantity") -> None:
    if not 1 <= quantity <= STOCK_QUANTITY_MAX:
        raise InvalidFieldError(field, "out_of_range", f"between 1 and {STOCK_QUANTITY_MAX}")


@dataclass(frozen=True, slots=True)
class WaitingOrder:
    """An order waiting for pieces of one Ausführung, and how many."""

    order_id: UUID
    number: str
    placed_at: datetime
    quantity: int


@dataclass(frozen=True, slots=True)
class ToMake:
    """An Ausführung the workshop must make for orders (*Zu fertigen*, ADR 0029)."""

    variant_id: UUID
    variant: SaleVariant | None
    quantity: int
    orders: list[WaitingOrder]
    """Oldest first."""

    @property
    def oldest_at(self) -> datetime:
        return self.orders[0].placed_at


class StockService:
    def __init__(self, *, uow_factory: UnitOfWorkFactory, clock: Clock) -> None:
        self._uow = uow_factory
        self._clock = clock

    # --- Reading --------------------------------------------------------------------

    async def places(
        self, *, product_id: UUID | None = None, location_code: str | None = None
    ) -> list[PlaceStock]:
        """Pieces per variant and place, free and reserved: of one model, in one place, or
        everywhere. In walking order of the places, then by model."""
        async with self._uow() as uow:
            variant_ids: set[UUID] | None = None
            if product_id is not None:
                variant_ids = {
                    v.variant_id for v in await uow.catalog.variants_of_product(product_id)
                }
            location_id: UUID | None = None
            if location_code is not None:
                location = await uow.locations.get_by_code(location_code.strip().upper())
                if location is None:
                    return []
                location_id = location.id
            counts = await uow.units.place_counts(variant_ids=variant_ids, location_id=location_id)
            locations = {location.id: location for location in await uow.locations.tree()}
            variants = await uow.catalog.variants({count.variant_id for count in counts})
        lines: dict[tuple[UUID, UUID], dict[UnitStatus, int]] = defaultdict(dict)
        for count in counts:
            lines[(count.location_id, count.variant_id)][count.status] = count.count
        result = [
            PlaceStock(
                location=locations[place_id],
                place=place_name(locations[place_id], locations),
                variant_id=variant_id,
                variant=variants.get(variant_id),
                free=by_status.get(UnitStatus.IN_STOCK, 0),
                reserved=by_status.get(UnitStatus.ALLOCATED, 0),
            )
            for (place_id, variant_id), by_status in lines.items()
            if place_id in locations
        ]
        result.sort(
            key=lambda line: (
                line.location.path,
                line.variant.title if line.variant else "",
                line.variant_id,
            )
        )
        return result

    async def products(self) -> list[ProductStock]:
        """Every model that has pieces or waiting orders: free, reserved, unbooked, waiting,
        and the places its pieces lie in."""
        async with self._uow() as uow:
            counts = await uow.units.place_counts()
            totals = await uow.units.counts()
            backorders = await uow.allocations.backorder_counts()
            locations = {location.id: location for location in await uow.locations.tree()}
            variants = await uow.catalog.variants(
                {c.variant_id for c in counts} | {t.variant_id for t in totals} | set(backorders)
            )
        free: dict[UUID, int] = defaultdict(int)
        reserved: dict[UUID, int] = defaultdict(int)
        labeled: dict[UUID, int] = defaultdict(int)
        waiting: dict[UUID, int] = defaultdict(int)
        places: dict[UUID, dict[UUID, int]] = defaultdict(lambda: defaultdict(int))
        for count in counts:
            variant = variants.get(count.variant_id)
            if variant is None:
                continue
            places[variant.product_id][count.location_id] += count.count
            if count.status is UnitStatus.IN_STOCK:
                free[variant.product_id] += count.count
            elif count.status is UnitStatus.ALLOCATED:
                reserved[variant.product_id] += count.count
        for total in totals:
            variant = variants.get(total.variant_id)
            if variant is not None and total.status is UnitStatus.LABELED:
                labeled[variant.product_id] += total.count
        for variant_id, number in backorders.items():
            variant = variants.get(variant_id)
            if variant is not None:
                waiting[variant.product_id] += number
        product_ids = set(places) | set(labeled) | set(waiting)
        return [
            ProductStock(
                product_id=product_id,
                free=free[product_id],
                reserved=reserved[product_id],
                labeled=labeled[product_id],
                backordered=waiting[product_id],
                places=sorted(
                    (
                        PlaceTotal(
                            location=locations[place_id],
                            place=place_name(locations[place_id], locations),
                            quantity=number,
                        )
                        for place_id, number in places[product_id].items()
                        if place_id in locations
                    ),
                    key=lambda total: (-total.quantity, total.location.path),
                ),
            )
            for product_id in sorted(product_ids)
        ]

    async def to_make(self) -> list[ToMake]:
        """Every Ausführung with pieces paid orders wait for, the longest waiting first.

        A piece booked in serves the oldest of them at once, so its row shrinks and goes.
        """
        async with self._uow() as uow:
            backorders = await uow.allocations.backorders()
            orders = await uow.orders.refs({allocation.order_id for allocation in backorders})
            variants = await uow.catalog.variants({a.variant_id for a in backorders})
        waiting: dict[UUID, dict[UUID, int]] = defaultdict(lambda: defaultdict(int))
        for allocation in backorders:
            order = orders.get(allocation.order_id)
            # Left over from an order that left or was cancelled: closed when stock comes.
            if order is not None and order.status is OrderStatus.PAID:
                waiting[allocation.variant_id][order.id] += 1
        rows = [
            ToMake(
                variant_id=variant_id,
                variant=variants.get(variant_id),
                quantity=sum(per_order.values()),
                orders=sorted(
                    (
                        WaitingOrder(
                            order_id=order_id,
                            number=orders[order_id].number,
                            placed_at=orders[order_id].placed_at,
                            quantity=quantity,
                        )
                        for order_id, quantity in per_order.items()
                    ),
                    key=lambda order: (order.placed_at, order.number),
                ),
            )
            for variant_id, per_order in waiting.items()
        ]
        rows.sort(key=lambda row: (row.oldest_at, row.variant.title if row.variant else ""))
        return rows

    async def history(self, product_id: UUID) -> list[HistoryRow]:
        """The model's latest bookings, newest first: journal entries of the same moment,
        person, kind, variant and way make one row with their number."""
        async with self._uow() as uow:
            variant_list = await uow.catalog.variants_of_product(product_id)
            if not variant_list:
                raise ProductNotFoundError
            variants = {variant.variant_id: variant for variant in variant_list}
            entries = await uow.ledger.latest_for_variants(variants, limit=HISTORY_ENTRIES)
            locations = {location.id: location for location in await uow.locations.tree()}
            names = await uow.staff.names({e.staff_id for e in entries if e.staff_id})
        groups: dict[tuple[object, ...], list[int]] = {}
        rows: list[HistoryRow] = []
        for entry in entries:
            key = (
                entry.occurred_at,
                entry.staff_id,
                entry.scan_id,
                entry.variant_id,
                entry.reason,
                entry.from_location_id,
                entry.to_location_id,
            )
            if key in groups:
                groups[key][0] += 1
                continue
            groups[key] = [1, len(rows)]
            source = locations.get(entry.from_location_id) if entry.from_location_id else None
            target = locations.get(entry.to_location_id) if entry.to_location_id else None
            rows.append(
                HistoryRow(
                    occurred_at=entry.occurred_at,
                    staff_name=names.get(entry.staff_id) if entry.staff_id else None,
                    reason=entry.reason,
                    variant_id=entry.variant_id,
                    variant=variants.get(entry.variant_id),
                    quantity=1,
                    from_location=source,
                    from_place=place_name(source, locations) if source else None,
                    to_location=target,
                    to_place=place_name(target, locations) if target else None,
                    scan=entry.scan_id is not None,
                )
            )
        for number, index in groups.values():
            rows[index] = replace(rows[index], quantity=number)
        return rows

    # --- Booking --------------------------------------------------------------------

    async def move(
        self,
        variant_id: UUID,
        *,
        from_code: str,
        to_code: str,
        quantity: int,
        staff_id: UUID | None,
    ) -> MoveResult:
        """``quantity`` pieces of the variant from one place to another, oldest first;
        reserved ones keep their order. All or none (:class:`NotEnoughPiecesError`)."""
        _check_quantity(quantity)
        async with self._uow() as uow:
            await _known_variant(uow, variant_id)
            source = await resolve_location(uow, from_code, "from_location")
            target = await resolve_location(uow, to_code, "to_location")
            if source.id == target.id:
                raise InvalidFieldError("to_location", "unchanged", "the same place")
            units = await lock_oldest(uow, variant_id, ON_SHELF, limit=quantity, location=source)
            if len(units) < quantity:
                raise NotEnoughPiecesError(len(units))
            journal = Journal(uow, staff_id=staff_id, now=self._clock.now())
            for unit in units:
                await put_away(uow, journal, unit, target)
            await uow.commit()
        return MoveResult(moved=len(units), source=source, target=target)

    async def scrap(
        self,
        variant_id: UUID,
        *,
        location_code: str | None,
        quantity: int,
        reason: ScrapReason,
        note: str,
        staff_id: UUID | None,
    ) -> ScrapResult:
        """``quantity`` free pieces of the variant leave the stock: from the place, else the
        oldest anywhere. Reserved pieces stay with their order; fewer free ones refuse
        the whole booking (:class:`NotEnoughFreeError`)."""
        _check_quantity(quantity)
        async with self._uow() as uow:
            await _known_variant(uow, variant_id)
            location = (
                await resolve_location(uow, location_code, "location_code")
                if location_code
                else None
            )
            units = await lock_oldest(
                uow, variant_id, UnitStatus.IN_STOCK, limit=quantity, location=location
            )
            if len(units) < quantity:
                raise NotEnoughFreeError(len(units))
            journal = Journal(uow, staff_id=staff_id, now=self._clock.now())
            sources: dict[UUID, int] = defaultdict(int)
            for unit in units:
                if unit.location_id is not None:
                    sources[unit.location_id] += 1
                await journal.book(unit, unit.scrap(note, journal.now, reason))
            locations = {location.id: location for location in await uow.locations.tree()}
            await uow.commit()
        return ScrapResult(
            scrapped=len(units),
            sources=[
                PlaceTotal(
                    location=locations[place_id],
                    place=place_name(locations[place_id], locations),
                    quantity=number,
                )
                for place_id, number in sorted(sources.items(), key=lambda item: str(item[0]))
                if place_id in locations
            ],
        )

    async def count(self, lines: Sequence[CountLine], *, staff_id: UUID | None) -> CountResult:
        """Set places to what was counted there, all lines in one go (*Zählen*).

        Each line names what the Stellwerk showed (``expected``: free and reserved pieces
        of the variant in the place) and what lies there. Fewer: free pieces go out as
        missing; if that would take reserved ones, nothing is booked
        (:class:`CountTakesReservedError` names the lines). More: new pieces are booked in
        there and serve waiting orders. If a place no longer holds what was expected,
        nothing is booked (:class:`CountOutdatedError`), so a count never undoes a booking
        made while counting.
        """
        _check_count(lines)
        async with self._uow() as uow:
            plans = await _plan_count(uow, lines)
            journal = Journal(uow, staff_id=staff_id, now=self._clock.now())
            gone = added = reserved = 0
            for plan in plans:
                for unit in plan.leaving:
                    note = f"Gezählt {plan.location.code}"
                    await journal.book(unit, unit.scrap(note, journal.now, ScrapReason.MISSING))
                gone += len(plan.leaving)
            # Only now: none of the missing pieces may stand in for a waiting order.
            await uow.flush()
            for plan in plans:
                if plan.extra > 0:
                    made = await label_new_units(
                        uow,
                        journal,
                        variant_id=plan.variant_id,
                        quantity=plan.extra,
                        location=plan.location,
                    )
                    added += len(made)
                    reserved += sum(1 for unit in made if unit.allocation_id is not None)
            await uow.commit()
        return CountResult(missing=gone, added=added, reserved=reserved)


@dataclass(frozen=True, slots=True)
class _CountPlan:
    variant_id: UUID
    location: Location
    leaving: list[Unit]
    """Free pieces that go out as missing, oldest first."""
    extra: int
    """New pieces to book in."""


def _check_count(lines: Sequence[CountLine]) -> None:
    if not 1 <= len(lines) <= COUNT_LINES_MAX:
        raise InvalidFieldError("lines", "out_of_range", f"1 to {COUNT_LINES_MAX} lines")
    keys = [(line.variant_id, line.location_code.strip().upper()) for line in lines]
    if len(set(keys)) != len(keys):
        raise InvalidFieldError("lines", "duplicate", "a variant and place twice")
    for index, line in enumerate(lines):
        if not 0 <= line.counted <= STOCK_QUANTITY_MAX or line.expected < 0:
            raise InvalidFieldError(
                f"lines.{index}.counted", "out_of_range", f"0 to {STOCK_QUANTITY_MAX}"
            )


async def _plan_count(uow: InventoryUnitOfWork, lines: Sequence[CountLine]) -> list[_CountPlan]:
    """What each line books, with every piece it touches locked in one go by id; refused
    as a whole if a place changed or would lose reserved pieces."""
    variants = await uow.catalog.variants({line.variant_id for line in lines})
    places: list[Location] = []
    ids: list[UUID] = []
    for index, line in enumerate(lines):
        if line.variant_id not in variants:
            raise InvalidFieldError(f"lines.{index}.variant_id", "unknown", "no such variant")
        location = await resolve_location(uow, line.location_code, f"lines.{index}.location_code")
        places.append(location)
        ids += await uow.units.oldest(
            line.variant_id, ON_SHELF, location_id=location.id, limit=None
        )
    locked = await uow.units.lock(ids)
    outdated: list[str] = []
    short: list[str] = []
    plans: list[_CountPlan] = []
    for line, location in zip(lines, places, strict=True):
        lying = [
            unit
            for unit in locked
            if unit.variant_id == line.variant_id
            and unit.location_id == location.id
            and unit.status in ON_SHELF
        ]
        # Put there after the first look: not locked, but still counts as changed.
        now_there = await uow.units.oldest(
            line.variant_id, ON_SHELF, location_id=location.id, limit=None
        )
        name = f"{variants[line.variant_id].sku} in {location.code}"
        if len(lying) != line.expected or len(now_there) != line.expected:
            outdated.append(name)
            continue
        free = sorted(
            (unit for unit in lying if unit.status is UnitStatus.IN_STOCK),
            key=lambda unit: (unit.created_at, unit.id),
        )
        missing = max(0, line.expected - line.counted)
        if missing > len(free):
            short.append(name)
            continue
        plans.append(
            _CountPlan(
                variant_id=line.variant_id,
                location=location,
                leaving=free[:missing],
                extra=max(0, line.counted - line.expected),
            )
        )
    if outdated:
        raise CountOutdatedError(outdated)
    if short:
        raise CountTakesReservedError(short)
    return plans


async def _known_variant(uow: InventoryUnitOfWork, variant_id: UUID) -> SaleVariant:
    variant = (await uow.catalog.variants([variant_id])).get(variant_id)
    if variant is None:
        raise VariantNotFoundError
    return variant
