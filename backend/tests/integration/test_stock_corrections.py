"""Putting the books right against a real PostgreSQL: booking scrapped units in again,
correcting a unit's variant, and counting a location (*Inventur*)."""

from datetime import timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine

from modellbahn.modules.catalog.application.services import CatalogService, ProductDetails
from modellbahn.modules.identity.application.services import IdentityService
from modellbahn.modules.inventory.application.allocation import AllocationService, PieceState
from modellbahn.modules.inventory.application.availability import AvailabilityService
from modellbahn.modules.inventory.application.locations import LocationService
from modellbahn.modules.inventory.application.scanning import ScanService
from modellbahn.modules.inventory.application.units import UnitService
from modellbahn.modules.inventory.domain.errors import (
    InvalidFieldError,
    LocationNotFoundError,
    StocktakeOutdatedError,
    UnitNotCorrectableError,
    UnitNotFoundError,
    UnitsNotMovableError,
    UnitsNotRestorableError,
    VariantNotFoundError,
)
from modellbahn.modules.inventory.domain.model import (
    UNITS_COUNTED_MAX,
    UNITS_SELECTED_MAX,
    LocationKind,
    MovementReason,
    ScrapReason,
    UnitStatus,
)
from modellbahn.modules.inventory.infrastructure.tables import stock_ledger
from modellbahn.modules.media.application.services import MediaService
from modellbahn.modules.sales.application.cart import CartService
from modellbahn.modules.sales.application.checkout import CheckoutService
from modellbahn.modules.sales.application.orders import OrderService
from modellbahn.platform.clock import FixedClock
from modellbahn.platform.outbox import outbox_table
from tests.conftest import Deliver
from tests.inventory_support import COMPARTMENT, pick_everything, staff_member, stock_up, store
from tests.media_support import InMemoryMediaStorage
from tests.sales_support import filled_cart, place, shop_product, variant_id

pytestmark = pytest.mark.usefixtures("clean_database")

OTHER = "R01-F02"


@pytest.fixture
async def product(
    catalog: CatalogService,
    media: MediaService,
    media_storage: InMemoryMediaStorage,
    deliver: Deliver,
) -> ProductDetails:
    """In stock, not made to order: without units it cannot be bought."""
    return await shop_product(catalog, media, media_storage, deliver, made_to_order=False)


@pytest.fixture
def painted(product: ProductDetails) -> UUID:
    return variant_id(product, "H0", "painted")


@pytest.fixture
def unpainted(product: ProductDetails) -> UUID:
    return variant_id(product, "H0", "unpainted")


@pytest.fixture
async def staff(identity: IdentityService) -> UUID:
    return await staff_member(identity)


@pytest.fixture
async def places(locations: LocationService) -> None:
    """The compartment R01-F01 and its neighbour R01-F02."""
    await store(locations)
    await locations.create(
        parent_code="R01", segment="F02", kind=LocationKind.COMPARTMENT, name="Oben"
    )


async def paid_order(
    carts: CartService, checkout: CheckoutService, *lines: tuple[UUID, int]
) -> UUID:
    cart = await filled_cart(carts, *lines)
    placed = (await place(checkout, carts, cart)).details.order
    await checkout.pay(public_token=placed.public_token, method="succeeds", idempotency_key=uuid4())
    return placed.id


async def unit_id(units: UnitService, code: str) -> UUID:
    return (await units.details(code)).view.unit.id


async def journal_size(engine: AsyncEngine) -> int:
    async with engine.connect() as connection:
        return int(await connection.scalar(select(func.count()).select_from(stock_ledger)) or 0)


async def stock_events(engine: AsyncEngine, reason: str) -> list[tuple[str, str, str]]:
    """``(unit code, variant id, status)`` of the stock events with ``reason``."""
    async with engine.connect() as connection:
        rows = await connection.execute(
            select(outbox_table.c.payload).where(
                outbox_table.c.event_type == "inventory.stock.changed",
                outbox_table.c.payload["reason"].astext == reason,
            )
        )
        return sorted((p["unit_code"], p["variant_id"], p["status"]) for (p,) in rows)


async def backorder_events(engine: AsyncEngine) -> int:
    async with engine.connect() as connection:
        return int(
            await connection.scalar(
                select(func.count())
                .select_from(outbox_table)
                .where(outbox_table.c.event_type == "inventory.allocation.backordered")
            )
            or 0
        )


@pytest.mark.usefixtures("places")
class TestBookingInAgain:
    """Scrapped by mistake, or turned up after all: *Wieder einbuchen*."""

    async def test_scrapped_units_come_back_free_and_serve_a_waiting_order(
        self,
        units: UnitService,
        locations: LocationService,
        catalog: CatalogService,
        carts: CartService,
        checkout: CheckoutService,
        allocation: AllocationService,
        availability: AvailabilityService,
        deliver: Deliver,
        engine: AsyncEngine,
        clock: FixedClock,
        product: ProductDetails,
        painted: UUID,
        staff: UUID,
    ) -> None:
        await catalog.change_variant(painted, expected_version=None, allow_backorder=True)
        first, second = await stock_up(locations, units, painted, quantity=2)
        ids = [await unit_id(units, code) for code in (first, second)]
        await units.scrap_units(ids, reason=ScrapReason.MISSING, note="Inventur", staff_id=staff)
        waiting = await paid_order(carts, checkout, (painted, 1))
        await deliver()
        (item,) = (await allocation.pick_list(waiting)).items
        assert item.state is PieceState.BACKORDERED
        clock.advance(timedelta(days=2))

        restore = await units.restore_units(ids, location_code="r01-f02", staff_id=staff)

        assert (restore.location.code, restore.restored, restore.already_there) == (OTHER, 2, 0)
        assert restore.reserved == 1
        (item,) = (await allocation.pick_list(waiting)).items
        assert (item.state, item.unit_code) in {
            (PieceState.RESERVED, first),
            (PieceState.RESERVED, second),
        }
        for code in (first, second):
            details = await units.details(code)
            unit = details.view.unit
            assert (unit.location_id, unit.scrap_reason, unit.scrap_note) == (
                restore.location.id,
                None,
                "",
            )
            back = next(h for h in details.history if h.entry.reason is MovementReason.RESTORE)
            assert (back.entry.from_status, back.entry.to_status) == (
                UnitStatus.SCRAPPED,
                UnitStatus.IN_STOCK,
            )
            assert back.to_location is not None
            assert (back.to_location.code, back.entry.staff_id, back.staff_name) == (
                OTHER,
                staff,
                "Lagerist",
            )
        free = {a.variant_id: a for a in await availability.for_product(product.product.slug)}
        assert free[painted].free_units == 1
        assert await stock_events(engine, "restore") == sorted(
            [(first, str(painted), "in_stock"), (second, str(painted), "in_stock")]
        )

        # Sent again (the answer got lost): nothing more happens.
        booked = await journal_size(engine)
        again = await units.restore_units(ids, location_code=OTHER, staff_id=staff)
        assert (again.restored, again.already_there, again.reserved) == (0, 2, 0)
        assert await journal_size(engine) == booked

    async def test_one_unit_that_is_not_scrapped_stops_them_all(
        self,
        units: UnitService,
        locations: LocationService,
        engine: AsyncEngine,
        painted: UUID,
        staff: UUID,
    ) -> None:
        gone, there = await stock_up(locations, units, painted, quantity=2)
        ids = [await unit_id(units, code) for code in (gone, there)]
        await units.scrap_units(ids[:1], reason=ScrapReason.DAMAGED, note="", staff_id=staff)
        booked = await journal_size(engine)

        with pytest.raises(UnitsNotRestorableError) as error:
            await units.restore_units(ids, location_code=OTHER, staff_id=staff)
        assert (error.value.refused, error.value.missing) == ({there: "in_stock"}, [])
        unknown = uuid4()
        with pytest.raises(UnitsNotRestorableError) as missing:
            await units.restore_units([ids[0], unknown], location_code=OTHER, staff_id=staff)
        assert missing.value.missing == [unknown]
        assert (await units.details(gone)).view.unit.status is UnitStatus.SCRAPPED
        assert await journal_size(engine) == booked

        with pytest.raises(LocationNotFoundError):
            await units.restore_units(ids[:1], location_code="R77", staff_id=staff)
        with pytest.raises(InvalidFieldError) as shelf:
            await units.restore_units(ids[:1], location_code="R01", staff_id=staff)
        assert (shelf.value.field, shelf.value.code) == ("location_code", "holds_no_goods")
        for count in (0, UNITS_SELECTED_MAX + 1):
            with pytest.raises(InvalidFieldError) as size:
                await units.restore_units(
                    [uuid4() for _ in range(count)], location_code=OTHER, staff_id=staff
                )
            assert size.value.code == "out_of_range"


@pytest.mark.usefixtures("places")
class TestCorrectingTheVariant:
    """A piece labelled as the wrong variant: *Ausführung ändern*."""

    async def test_a_free_unit_becomes_the_other_variant_where_it_lies(
        self,
        units: UnitService,
        locations: LocationService,
        availability: AvailabilityService,
        engine: AsyncEngine,
        product: ProductDetails,
        painted: UUID,
        unpainted: UUID,
        staff: UUID,
    ) -> None:
        (code,) = await stock_up(locations, units, painted)
        before = (await units.details(code)).view

        view = await units.correct(code.lower(), variant_id=unpainted, staff_id=staff)

        assert (view.unit.variant_id, view.unit.status, view.unit.code) == (
            unpainted,
            UnitStatus.IN_STOCK,
            code,
        )
        assert view.location is not None
        assert view.location.code == COMPARTMENT
        # The EAN on the label is the variant's: it has changed.
        assert view.variant is not None
        assert before.variant is not None
        assert view.variant.gtin != before.variant.gtin
        last = (await units.details(code)).history[-1]
        assert (last.entry.reason, last.entry.variant_id, last.entry.staff_id) == (
            MovementReason.CORRECT,
            unpainted,
            staff,
        )
        assert (last.entry.from_location_id, last.entry.to_location_id) == (
            view.unit.location_id,
            view.unit.location_id,
        )
        assert last.from_variant is not None
        assert last.to_variant is not None
        assert (last.from_variant.variant_id, last.to_variant.variant_id) == (painted, unpainted)
        free = {a.variant_id: a for a in await availability.for_product(product.product.slug)}
        assert (free[painted].free_units, free[unpainted].free_units) == (0, 1)
        # Both articles hear of it: screens and eBay count again.
        assert await stock_events(engine, "correct") == sorted(
            [(code, str(painted), "in_stock"), (code, str(unpainted), "in_stock")]
        )

    async def test_a_labelled_unit_stays_unbooked_a_free_one_serves_a_waiting_order(
        self,
        units: UnitService,
        locations: LocationService,
        catalog: CatalogService,
        carts: CartService,
        checkout: CheckoutService,
        allocation: AllocationService,
        deliver: Deliver,
        painted: UUID,
        unpainted: UUID,
        staff: UUID,
    ) -> None:
        (labelled,) = await units.label_units(
            variant_id=painted, quantity=1, location_code=None, staff_id=None
        )
        unbooked = await units.correct(labelled.unit.code, variant_id=unpainted, staff_id=staff)
        assert (unbooked.unit.status, unbooked.unit.location_id) == (UnitStatus.LABELED, None)

        await catalog.change_variant(unpainted, expected_version=None, allow_backorder=True)
        waiting = await paid_order(carts, checkout, (unpainted, 1))
        await deliver()
        (code,) = await stock_up(locations, units, painted)
        view = await units.correct(code, variant_id=unpainted, staff_id=staff)
        assert (view.unit.status, view.order_id) == (UnitStatus.ALLOCATED, waiting)
        (item,) = (await allocation.pick_list(waiting)).items
        assert (item.state, item.unit_code) == (PieceState.RESERVED, code)

    async def test_units_an_order_had_stay_what_they_are(
        self,
        units: UnitService,
        locations: LocationService,
        carts: CartService,
        checkout: CheckoutService,
        orders: OrderService,
        allocation: AllocationService,
        scans: ScanService,
        deliver: Deliver,
        engine: AsyncEngine,
        painted: UUID,
        unpainted: UUID,
        staff: UUID,
    ) -> None:
        codes = await stock_up(locations, units, painted, quantity=2)
        first = await paid_order(carts, checkout, (painted, 1))
        await deliver()
        picked = (await pick_everything(scans, allocation, first, staff)).items[0].unit_code
        assert picked is not None
        (reserved,) = set(codes) - {picked}
        await paid_order(carts, checkout, (painted, 1))
        await deliver()
        (scrapped,) = await stock_up(locations, units, painted)
        await units.scrap(scrapped, note="", reason=ScrapReason.DAMAGED, staff_id=staff)
        booked = await journal_size(engine)

        for code, status in (
            (reserved, UnitStatus.ALLOCATED),
            (picked, UnitStatus.PICKED),
            (scrapped, UnitStatus.SCRAPPED),
        ):
            assert (await units.details(code)).view.unit.status is status
            with pytest.raises(UnitNotCorrectableError) as error:
                await units.correct(code, variant_id=unpainted, staff_id=staff)
            assert error.value.status == status.value

        # Picked, then the order was cancelled and the piece put back: it stays as it was.
        await orders.cancel(first, note="")
        await deliver()
        assert (await units.details(picked)).view.unit.status is UnitStatus.LABELED
        await units.move_units(
            [await unit_id(units, picked)], location_code=COMPARTMENT, staff_id=staff
        )
        with pytest.raises(UnitNotCorrectableError):
            await units.correct(picked, variant_id=unpainted, staff_id=staff)
        assert await journal_size(engine) == booked + 2  # the release and the put-away

        (free,) = await stock_up(locations, units, painted)
        with pytest.raises(InvalidFieldError) as same:
            await units.correct(free, variant_id=painted, staff_id=staff)
        assert same.value.code == "unchanged"
        with pytest.raises(VariantNotFoundError):
            await units.correct(free, variant_id=uuid4(), staff_id=staff)
        with pytest.raises(UnitNotFoundError):
            await units.correct("0000000000", variant_id=unpainted, staff_id=staff)


@pytest.mark.usefixtures("places")
class TestStocktake:
    """Counting one location: *Inventur*."""

    async def test_missing_go_out_found_come_in_confirmed_stay(
        self,
        units: UnitService,
        locations: LocationService,
        catalog: CatalogService,
        carts: CartService,
        checkout: CheckoutService,
        allocation: AllocationService,
        deliver: Deliver,
        engine: AsyncEngine,
        clock: FixedClock,
        painted: UUID,
        unpainted: UUID,
        staff: UUID,
    ) -> None:
        await catalog.change_variant(unpainted, expected_version=None, allow_backorder=True)
        present, lost = await stock_up(locations, units, painted, quantity=2)
        (reserved,) = await stock_up(locations, units, unpainted)
        waiting = await paid_order(carts, checkout, (unpainted, 1))
        await deliver()
        assert (await allocation.pick_list(waiting)).items[0].unit_code == reserved
        clock.advance(timedelta(minutes=1))
        (elsewhere,) = await units.label_units(
            variant_id=painted, quantity=1, location_code=OTHER, staff_id=None
        )
        (unbooked,) = await units.label_units(
            variant_id=painted, quantity=1, location_code=None, staff_id=None
        )
        (written_off,) = await stock_up(locations, units, painted)
        await units.scrap(written_off, note="", reason=ScrapReason.MISSING, staff_id=staff)
        request = {
            "present": [await unit_id(units, present)],
            "missing": [await unit_id(units, lost), await unit_id(units, reserved)],
            "found": [
                elsewhere.unit.id,
                unbooked.unit.id,
                await unit_id(units, written_off),
            ],
        }

        result = await units.take_stock("r01-f01", **request, staff_id=staff)

        assert (result.location.code, result.confirmed, result.scrapped, result.found) == (
            COMPARTMENT,
            1,
            2,
            3,
        )
        assert result.reserved == 0
        inside = {unit.code for unit in (await locations.contents(COMPARTMENT)).units}
        assert inside == {present, elsewhere.unit.code, unbooked.unit.code, written_off}
        for code in (lost, reserved):
            unit = (await units.details(code)).view.unit
            assert (unit.status, unit.scrap_reason, unit.scrap_note) == (
                UnitStatus.SCRAPPED,
                ScrapReason.MISSING,
                "Inventur R01-F01",
            )
        for code, reason in (
            (elsewhere.unit.code, MovementReason.MOVE),
            (unbooked.unit.code, MovementReason.PUT_AWAY),
            (written_off, MovementReason.RESTORE),
            (lost, MovementReason.SCRAP),
        ):
            last = (await units.details(code)).history[-1]
            assert (last.entry.reason, last.entry.staff_id) == (reason, staff)
        assert (await units.details(written_off)).view.unit.scrap_reason is None
        assert (await units.details(present)).history[-1].entry.reason is MovementReason.PUT_AWAY
        # The order whose piece is missing waits for the workshop: no other piece is there.
        (item,) = (await allocation.pick_list(waiting)).items
        assert item.state is PieceState.BACKORDERED
        assert await backorder_events(engine) == 1

        # Sent again (the answer got lost): nothing more happens.
        booked = await journal_size(engine)
        again = await units.take_stock(COMPARTMENT, **request, staff_id=staff)
        assert (again.confirmed, again.scrapped, again.found) == (1, 0, 0)
        assert await journal_size(engine) == booked

    async def test_a_found_unit_goes_to_the_order_waiting_for_it(
        self,
        units: UnitService,
        locations: LocationService,
        catalog: CatalogService,
        carts: CartService,
        checkout: CheckoutService,
        allocation: AllocationService,
        deliver: Deliver,
        painted: UUID,
        staff: UUID,
    ) -> None:
        await catalog.change_variant(painted, expected_version=None, allow_backorder=True)
        waiting = await paid_order(carts, checkout, (painted, 1))
        await deliver()
        (unbooked,) = await units.label_units(
            variant_id=painted, quantity=1, location_code=None, staff_id=None
        )
        result = await units.take_stock(
            COMPARTMENT, present=[], missing=[], found=[unbooked.unit.id], staff_id=staff
        )
        assert (result.found, result.reserved) == (1, 1)
        (item,) = (await allocation.pick_list(waiting)).items
        assert (item.state, item.unit_code) == (PieceState.RESERVED, unbooked.unit.code)

    async def test_a_location_that_changed_during_the_count_books_nothing(
        self,
        units: UnitService,
        locations: LocationService,
        engine: AsyncEngine,
        painted: UUID,
        staff: UUID,
    ) -> None:
        counted, lost = await stock_up(locations, units, painted, quantity=2)
        ids = {code: await unit_id(units, code) for code in (counted, lost)}
        # While counting, somebody puts a piece there.
        (late,) = await stock_up(locations, units, painted)
        booked = await journal_size(engine)

        with pytest.raises(StocktakeOutdatedError) as arrived:
            await units.take_stock(
                COMPARTMENT, present=[ids[counted]], missing=[ids[lost]], found=[], staff_id=staff
            )
        assert arrived.value.refused == {late: "in_stock"}
        assert await journal_size(engine) == booked
        # Somebody takes a counted piece away: the count is outdated as well.
        await units.move_units([ids[counted]], location_code=OTHER, staff_id=staff)
        late_id = await unit_id(units, late)
        booked = await journal_size(engine)
        with pytest.raises(StocktakeOutdatedError) as left:
            await units.take_stock(
                COMPARTMENT,
                present=[ids[counted], late_id],
                missing=[ids[lost]],
                found=[],
                staff_id=staff,
            )
        assert left.value.refused == {counted: "in_stock"}
        assert (await units.details(lost)).view.unit.status is UnitStatus.IN_STOCK
        assert await journal_size(engine) == booked

    async def test_a_found_unit_of_an_order_stops_the_count(
        self,
        units: UnitService,
        locations: LocationService,
        carts: CartService,
        checkout: CheckoutService,
        allocation: AllocationService,
        scans: ScanService,
        deliver: Deliver,
        engine: AsyncEngine,
        painted: UUID,
        staff: UUID,
    ) -> None:
        (packed,) = await stock_up(locations, units, painted)
        order_id = await paid_order(carts, checkout, (painted, 1))
        await deliver()
        await pick_everything(scans, allocation, order_id, staff)
        (unbooked,) = await units.label_units(
            variant_id=painted, quantity=1, location_code=None, staff_id=None
        )
        booked = await journal_size(engine)
        unknown = uuid4()
        with pytest.raises(UnitsNotMovableError) as error:
            await units.take_stock(
                OTHER,
                present=[],
                missing=[],
                found=[unbooked.unit.id, await unit_id(units, packed), unknown],
                staff_id=staff,
            )
        assert (error.value.refused, error.value.missing) == ({packed: "picked"}, [unknown])
        assert (await units.details(unbooked.unit.code)).view.unit.status is UnitStatus.LABELED
        assert await journal_size(engine) == booked

    async def test_refusals(self, units: UnitService, painted: UUID, staff: UUID) -> None:
        with pytest.raises(LocationNotFoundError):
            await units.take_stock("R77", present=[], missing=[], found=[], staff_id=staff)
        with pytest.raises(InvalidFieldError) as shelf:
            await units.take_stock("R01", present=[], missing=[], found=[], staff_id=staff)
        assert (shelf.value.field, shelf.value.code) == ("code", "holds_no_goods")
        twice = uuid4()
        with pytest.raises(InvalidFieldError) as duplicate:
            await units.take_stock(
                COMPARTMENT, present=[twice], missing=[], found=[twice], staff_id=staff
            )
        assert duplicate.value.code == "duplicate"
        with pytest.raises(InvalidFieldError) as size:
            await units.take_stock(
                COMPARTMENT,
                present=[uuid4() for _ in range(UNITS_COUNTED_MAX + 1)],
                missing=[],
                found=[],
                staff_id=staff,
            )
        assert size.value.code == "out_of_range"
        # An empty place counted empty: nothing to book.
        empty = await units.take_stock(OTHER, present=[], missing=[], found=[], staff_id=staff)
        assert (empty.confirmed, empty.scrapped, empty.found) == (0, 0, 0)
