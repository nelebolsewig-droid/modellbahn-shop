"""The inventory use cases against a real PostgreSQL: locations, units, allocation, scans."""

from datetime import timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine

from modellbahn.modules.catalog.application.services import CatalogService, ProductDetails
from modellbahn.modules.catalog.domain.errors import VariantHasUnitsError
from modellbahn.modules.identity.application.services import IdentityService
from modellbahn.modules.inventory.application.allocation import AllocationService, PieceState
from modellbahn.modules.inventory.application.availability import AvailabilityService
from modellbahn.modules.inventory.application.locations import LocationService
from modellbahn.modules.inventory.application.scanning import ScanService
from modellbahn.modules.inventory.application.units import UnitService
from modellbahn.modules.inventory.domain.availability import Availability
from modellbahn.modules.inventory.domain.errors import (
    InvalidFieldError,
    InvalidUnitStateError,
    LocationCodeTakenError,
    LocationInUseError,
    LocationNotEmptyError,
    LocationNotFoundError,
    OrderNotAllocatableError,
    OrderNotFoundError,
    ProductNotFoundError,
    ScanIdReusedError,
    ScanNotFoundError,
    ScanNotUndoableError,
    UnitNotFoundError,
    VariantNotFoundError,
)
from modellbahn.modules.inventory.domain.model import (
    UNDO_WINDOW_SECONDS,
    LocationKind,
    ScanMode,
    UnitStatus,
)
from modellbahn.modules.inventory.infrastructure.tables import stock_ledger
from modellbahn.modules.media.application.services import MediaService
from modellbahn.modules.sales.application.cart import CartService
from modellbahn.modules.sales.application.checkout import CheckoutService
from modellbahn.modules.sales.application.orders import OrderService
from modellbahn.modules.sales.domain.errors import InsufficientStockError
from modellbahn.platform.clock import FixedClock
from modellbahn.platform.outbox import outbox_table
from tests.conftest import Deliver
from tests.inventory_support import (
    COMPARTMENT,
    pick_everything,
    scan,
    staff_member,
    stock_up,
    store,
)
from tests.media_support import InMemoryMediaStorage
from tests.sales_support import filled_cart, place, shop_product, variant_id

pytestmark = pytest.mark.usefixtures("clean_database")


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


async def order(
    carts: CartService, checkout: CheckoutService, *lines: tuple[UUID, int], pay: bool = True
) -> UUID:
    cart = await filled_cart(carts, *lines)
    placed = (await place(checkout, carts, cart)).details.order
    if pay:
        await checkout.pay(
            public_token=placed.public_token, method="succeeds", idempotency_key=uuid4()
        )
    return placed.id


async def journal_size(engine: AsyncEngine) -> int:
    async with engine.connect() as connection:
        return int(await connection.scalar(select(func.count()).select_from(stock_ledger)) or 0)


class TestLocations:
    async def test_the_tree_with_codes_paths_and_counts(
        self, locations: LocationService, units: UnitService, painted: UUID
    ) -> None:
        await store(locations)
        box = await locations.create(
            parent_code="R01-F01", segment="b1", kind=LocationKind.BOX, name="Kleinteile"
        )
        await locations.create(
            parent_code="LAGER", segment="PACK", kind=LocationKind.STAGING, name="Packtisch"
        )
        assert (box.code, box.path) == ("R01-F01-B1", "LAGER.R01.F01.B1")
        await units.label_units(
            variant_id=painted, quantity=2, location_code="r01-f01-b1", staff_id=None
        )
        await units.label_units(
            variant_id=painted, quantity=1, location_code=COMPARTMENT, staff_id=None
        )

        tree = await locations.tree()
        assert [(n.location.code, n.unit_count, n.total_count) for n in tree] == [
            ("LAGER", 0, 3),
            ("PACK", 0, 0),
            ("R01", 0, 3),
            ("R01-F01", 1, 3),
            ("R01-F01-B1", 2, 2),
        ]

        contents = await locations.contents("R01-F01")
        assert [a.code for a in contents.ancestors] == ["LAGER", "R01"]
        assert [c.location.code for c in contents.children] == ["R01-F01-B1"]
        assert len(contents.units) == 3
        assert {u.variant_id for u in contents.units} == {painted}

    async def test_refusals(self, locations: LocationService) -> None:
        await store(locations)
        with pytest.raises(LocationNotFoundError):
            await locations.create(
                parent_code="R09", segment="F1", kind=LocationKind.COMPARTMENT, name=""
            )
        with pytest.raises(LocationCodeTakenError):
            await locations.create(
                parent_code="LAGER", segment="R01", kind=LocationKind.SHELF, name=""
            )
        with pytest.raises(InvalidFieldError):
            await locations.create(
                parent_code="LAGER", segment="F1", kind=LocationKind.BOX, name=""
            )
        with pytest.raises(LocationNotFoundError):
            await locations.rename("NIRGENDS", name="x")
        with pytest.raises(LocationNotFoundError):
            await locations.contents("NIRGENDS")
        with pytest.raises(LocationNotFoundError):
            await locations.remove("NIRGENDS")

    async def test_rename_and_remove(
        self, locations: LocationService, units: UnitService, painted: UUID
    ) -> None:
        await store(locations)
        renamed = await locations.rename("R01", name="Regal am Fenster")
        assert (renamed.code, renamed.name) == ("R01", "Regal am Fenster")
        with pytest.raises(LocationNotEmptyError):
            await locations.remove("R01")
        spare = await locations.create(
            parent_code="R01", segment="F02", kind=LocationKind.COMPARTMENT, name=""
        )
        await locations.remove(spare.code)
        # Goods were here once: the location keeps its history.
        (code,) = await stock_up(locations, units, painted)
        await units.scrap(code, note="zerbrochen", staff_id=None)
        with pytest.raises(LocationInUseError):
            await locations.remove(COMPARTMENT)


class TestUnits:
    async def test_labelling_without_and_with_a_location(
        self, locations: LocationService, units: UnitService, painted: UUID, engine: AsyncEngine
    ) -> None:
        loose = await units.label_units(
            variant_id=painted, quantity=2, location_code=None, staff_id=None
        )
        assert [v.unit.status for v in loose] == [UnitStatus.LABELED] * 2
        assert len({v.unit.code for v in loose}) == 2
        stored = await units.label_units(
            variant_id=painted, quantity=1, location_code=await store(locations), staff_id=None
        )
        assert (stored[0].unit.status, stored[0].location.code) == (  # type: ignore[union-attr]
            UnitStatus.IN_STOCK,
            COMPARTMENT,
        )
        # Labelling and putting away are both booked.
        assert await journal_size(engine) == 4

    async def test_refusals(
        self, locations: LocationService, units: UnitService, painted: UUID
    ) -> None:
        await store(locations)
        with pytest.raises(VariantNotFoundError):
            await units.label_units(
                variant_id=uuid4(), quantity=1, location_code=None, staff_id=None
            )
        with pytest.raises(InvalidFieldError):
            await units.label_units(
                variant_id=painted, quantity=0, location_code=None, staff_id=None
            )
        with pytest.raises(InvalidFieldError):
            await units.label_units(
                variant_id=painted, quantity=1, location_code="R01", staff_id=None
            )
        with pytest.raises(LocationNotFoundError):
            await units.label_units(
                variant_id=painted, quantity=1, location_code="X1", staff_id=None
            )
        with pytest.raises(UnitNotFoundError):
            await units.details("0000000000")
        with pytest.raises(UnitNotFoundError):
            await units.scrap("0000000000", note="", staff_id=None)

    async def test_details_tell_the_whole_story(
        self,
        locations: LocationService,
        units: UnitService,
        scans: ScanService,
        painted: UUID,
        staff: UUID,
    ) -> None:
        await store(locations)
        (view,) = await units.label_units(
            variant_id=painted, quantity=1, location_code=None, staff_id=staff
        )
        await scan(
            scans, staff, view.unit.code, ScanMode.PUT_AWAY, context={"location_code": COMPARTMENT}
        )
        details = await units.details(view.unit.code.lower())
        assert details.view.unit.status is UnitStatus.IN_STOCK
        assert [(h.entry.reason.value, h.staff_name) for h in details.history] == [
            ("label", "Lagerist"),
            ("put_away", "Lagerist"),
        ]
        assert details.history[1].to_location.code == COMPARTMENT  # type: ignore[union-attr]

    async def test_stock_lists_every_state_and_the_backorders(
        self,
        locations: LocationService,
        units: UnitService,
        carts: CartService,
        checkout: CheckoutService,
        deliver: Deliver,
        painted: UUID,
        unpainted: UUID,
    ) -> None:
        await stock_up(locations, units, painted, quantity=3)
        await units.label_units(variant_id=unpainted, quantity=1, location_code=None, staff_id=None)
        await order(carts, checkout, (painted, 2))
        await deliver()
        lines = {line.variant_id: line for line in await units.stock()}
        assert (lines[painted].in_stock, lines[painted].allocated) == (1, 2)
        assert (lines[unpainted].labeled, lines[unpainted].in_stock) == (1, 0)


class TestAllocation:
    async def test_a_paid_order_takes_the_oldest_units_first(
        self,
        locations: LocationService,
        units: UnitService,
        carts: CartService,
        checkout: CheckoutService,
        allocation: AllocationService,
        deliver: Deliver,
        clock: FixedClock,
        painted: UUID,
    ) -> None:
        oldest = await stock_up(locations, units, painted, quantity=2)
        clock.advance(timedelta(days=1))
        await stock_up(locations, units, painted, quantity=2)
        order_id = await order(carts, checkout, (painted, 2))
        await deliver()

        pick_list = await allocation.pick_list(order_id)
        assert sorted(item.unit_code for item in pick_list.items) == sorted(oldest)  # type: ignore[type-var]
        assert {item.state for item in pick_list.items} == {PieceState.RESERVED}
        assert (pick_list.picked, pick_list.total, pick_list.is_complete) == (0, 2, False)
        # Running again (a repeated event, a click) changes nothing.
        again = await allocation.allocate_order(order_id)
        assert [i.allocation_id for i in again.items] == [i.allocation_id for i in pick_list.items]

    async def test_missing_pieces_are_backordered_and_get_the_next_unit(
        self,
        locations: LocationService,
        units: UnitService,
        catalog: CatalogService,
        carts: CartService,
        checkout: CheckoutService,
        allocation: AllocationService,
        deliver: Deliver,
        engine: AsyncEngine,
        painted: UUID,
    ) -> None:
        await catalog.change_variant(painted, expected_version=None, allow_backorder=True)
        await stock_up(locations, units, painted)
        first = await order(carts, checkout, (painted, 2))
        second = await order(carts, checkout, (painted, 1))
        await deliver()
        states = [i.state for i in (await allocation.pick_list(first)).items]
        assert sorted(states) == [PieceState.BACKORDERED, PieceState.RESERVED]
        async with engine.connect() as connection:
            backordered = await connection.scalar(
                select(func.count())
                .select_from(outbox_table)
                .where(outbox_table.c.event_type == "inventory.allocation.backordered")
            )
        assert backordered == 2

        # The next unit put away goes to the order waiting longest.
        await stock_up(locations, units, painted)
        assert (await allocation.pick_list(first)).next_expected() is not None
        assert {i.state for i in (await allocation.pick_list(first)).items} == {PieceState.RESERVED}
        assert [i.state for i in (await allocation.pick_list(second)).items] == [
            PieceState.BACKORDERED
        ]

    async def test_cancelling_gives_the_units_back(
        self,
        locations: LocationService,
        units: UnitService,
        catalog: CatalogService,
        carts: CartService,
        checkout: CheckoutService,
        orders: OrderService,
        allocation: AllocationService,
        scans: ScanService,
        deliver: Deliver,
        painted: UUID,
        staff: UUID,
    ) -> None:
        await catalog.change_variant(painted, expected_version=None, allow_backorder=True)
        await stock_up(locations, units, painted, quantity=2)
        first = await order(carts, checkout, (painted, 2))
        waiting = await order(carts, checkout, (painted, 1))
        await deliver()
        pick_list = await allocation.pick_list(first)
        picked_code = pick_list.items[0].unit_code
        await scan(scans, staff, str(picked_code), ScanMode.PICK, context={"order_id": str(first)})

        await orders.cancel(first, note="")
        await deliver()
        assert {i.state for i in (await allocation.pick_list(first)).items} == {PieceState.RELEASED}
        # The reserved one went straight to the waiting order; the picked one must be
        # put away again before anybody gets it.
        assert [i.state for i in (await allocation.pick_list(waiting)).items] == [
            PieceState.RESERVED
        ]
        picked = await units.details(str(picked_code))
        assert picked.view.unit.status is UnitStatus.LABELED
        # Releasing again (a repeated event) changes nothing.
        await allocation.release_order(first)

    async def test_shipping_takes_the_units_along(
        self,
        locations: LocationService,
        units: UnitService,
        carts: CartService,
        checkout: CheckoutService,
        orders: OrderService,
        allocation: AllocationService,
        scans: ScanService,
        deliver: Deliver,
        painted: UUID,
        staff: UUID,
    ) -> None:
        codes = await stock_up(locations, units, painted)
        order_id = await order(carts, checkout, (painted, 1))
        await deliver()
        assert (await pick_everything(scans, allocation, order_id, staff)).is_complete
        await orders.ship(order_id, carrier="DHL", tracking_number="1")
        await deliver()
        assert (await units.details(codes[0])).view.unit.status is UnitStatus.SHIPPED
        assert [i.state for i in (await allocation.pick_list(order_id)).items] == [
            PieceState.SHIPPED
        ]
        await allocation.ship_order(order_id)

    async def test_only_paid_orders_are_allocated(
        self,
        locations: LocationService,
        units: UnitService,
        carts: CartService,
        checkout: CheckoutService,
        allocation: AllocationService,
        painted: UUID,
    ) -> None:
        await stock_up(locations, units, painted)
        unpaid = await order(carts, checkout, (painted, 1), pay=False)
        with pytest.raises(OrderNotAllocatableError):
            await allocation.allocate_order(unpaid)
        with pytest.raises(OrderNotFoundError):
            await allocation.allocate_order(uuid4())
        with pytest.raises(OrderNotFoundError):
            await allocation.pick_list(uuid4())

    async def test_an_order_paid_before_the_workshop_allocated_can_be_allocated_by_hand(
        self,
        locations: LocationService,
        units: UnitService,
        carts: CartService,
        checkout: CheckoutService,
        allocation: AllocationService,
        painted: UUID,
    ) -> None:
        await stock_up(locations, units, painted)
        order_id = await order(carts, checkout, (painted, 1))
        assert not (await allocation.pick_list(order_id)).is_allocated
        allocated = await allocation.allocate_order(order_id, staff_id=None)
        assert [i.state for i in allocated.items] == [PieceState.RESERVED]

    async def test_scrapping_a_reserved_unit_reserves_another(
        self,
        locations: LocationService,
        units: UnitService,
        carts: CartService,
        checkout: CheckoutService,
        allocation: AllocationService,
        deliver: Deliver,
        painted: UUID,
    ) -> None:
        await stock_up(locations, units, painted, quantity=2)
        order_id = await order(carts, checkout, (painted, 1))
        await deliver()
        (item,) = (await allocation.pick_list(order_id)).items
        scrapped = await units.scrap(str(item.unit_code), note="Dach gebrochen", staff_id=None)
        assert (scrapped.unit.status, scrapped.unit.scrap_note) == (
            UnitStatus.SCRAPPED,
            "Dach gebrochen",
        )
        (replacement,) = (await allocation.pick_list(order_id)).items
        assert replacement.state is PieceState.RESERVED
        assert replacement.unit_code != item.unit_code
        with pytest.raises(InvalidUnitStateError):
            await units.scrap(str(item.unit_code), note="", staff_id=None)


class TestPutAwayScans:
    async def test_location_then_units(
        self,
        locations: LocationService,
        units: UnitService,
        scans: ScanService,
        painted: UUID,
        staff: UUID,
    ) -> None:
        await store(locations)
        await locations.create(
            parent_code="R01", segment="F02", kind=LocationKind.COMPARTMENT, name=""
        )
        (view,) = await units.label_units(
            variant_id=painted, quantity=1, location_code=None, staff_id=None
        )
        chosen = await scan(scans, staff, "https://shop.example/l/r01-f01", ScanMode.PUT_AWAY)
        assert (chosen["outcome"], chosen["message"]) == ("selected", "location_selected")
        stored = await scan(
            scans, staff, view.unit.code, ScanMode.PUT_AWAY, context={"location_code": COMPARTMENT}
        )
        assert (stored["outcome"], stored["message"]) == ("applied", "put_away")
        assert stored["effect"]["to_location"] == COMPARTMENT  # type: ignore[index,call-overload]
        assert stored["undoable"] is True
        moved = await scan(
            scans, staff, view.unit.code, ScanMode.PUT_AWAY, context={"location_code": "R01-F02"}
        )
        assert (moved["message"], moved["effect"]["from_location"]) == ("move", COMPARTMENT)  # type: ignore[index,call-overload]
        again = await scan(
            scans, staff, view.unit.code, ScanMode.PUT_AWAY, context={"location_code": "R01-F02"}
        )
        assert (again["outcome"], again["message"]) == ("rejected", "already_there")

    @pytest.mark.parametrize(
        ("raw", "context", "message"),
        [
            ("unit", {}, "location_required"),
            ("unit", {"location_code": "R77"}, "location_unknown"),
            ("unit", {"location_code": "R01"}, "holds_no_goods"),
            ("R01", {}, "holds_no_goods"),
            ("Hallo Welt", {}, "unknown_code"),
            ("R77-F01", {}, "not_found"),
        ],
    )
    async def test_refusals(
        self,
        locations: LocationService,
        units: UnitService,
        scans: ScanService,
        painted: UUID,
        staff: UUID,
        raw: str,
        context: dict[str, str],
        message: str,
    ) -> None:
        await store(locations)
        (view,) = await units.label_units(
            variant_id=painted, quantity=1, location_code=None, staff_id=None
        )
        answer = await scan(
            scans,
            staff,
            view.unit.code if raw == "unit" else raw,
            ScanMode.PUT_AWAY,
            context=context,
        )
        assert answer["message"] == message
        assert answer["undoable"] is False

    async def test_the_articles_ean_stores_its_oldest_labelled_unit(
        self,
        locations: LocationService,
        units: UnitService,
        scans: ScanService,
        product: ProductDetails,
        painted: UUID,
        staff: UUID,
    ) -> None:
        await store(locations)
        (first,) = await units.label_units(
            variant_id=painted, quantity=1, location_code=None, staff_id=None
        )
        gtin = next(v.gtin for s in product.product.scales for v in s.variants if v.id == painted)
        context = {"location_code": COMPARTMENT}
        stored = await scan(scans, staff, gtin, ScanMode.PUT_AWAY, context=context)
        assert (stored["outcome"], stored["unit"]["code"]) == ("applied", first.unit.code)  # type: ignore[index,call-overload]
        nothing = await scan(scans, staff, gtin, ScanMode.PUT_AWAY, context=context)
        assert nothing["message"] == "no_unit_to_store"

    async def test_lookups_book_nothing(
        self,
        locations: LocationService,
        units: UnitService,
        scans: ScanService,
        product: ProductDetails,
        painted: UUID,
        staff: UUID,
    ) -> None:
        (code,) = await stock_up(locations, units, painted)
        gtin = next(v.gtin for s in product.product.scales for v in s.variants if v.id == painted)
        unit = await scan(scans, staff, code, ScanMode.LOOKUP)
        location = await scan(scans, staff, COMPARTMENT, ScanMode.LOOKUP)
        variant = await scan(scans, staff, gtin, ScanMode.LOOKUP)
        assert [a["message"] for a in (unit, location, variant)] == ["unit", "location", "variant"]
        assert unit["unit"]["location_code"] == COMPARTMENT  # type: ignore[index,call-overload]
        assert location["location"]["unit_count"] == 1  # type: ignore[index,call-overload]
        assert variant["variant"]["free_units"] == 1  # type: ignore[index,call-overload]


class TestPickScans:
    async def setup_order(
        self,
        locations: LocationService,
        units: UnitService,
        carts: CartService,
        checkout: CheckoutService,
        deliver: Deliver,
        painted: UUID,
        quantity: int = 2,
    ) -> tuple[UUID, list[str]]:
        codes = await stock_up(locations, units, painted, quantity=quantity + 1)
        order_id = await order(carts, checkout, (painted, quantity))
        await deliver()
        return order_id, codes

    async def test_each_reserved_unit_once_with_progress(
        self,
        locations: LocationService,
        units: UnitService,
        carts: CartService,
        checkout: CheckoutService,
        allocation: AllocationService,
        scans: ScanService,
        deliver: Deliver,
        painted: UUID,
        staff: UUID,
    ) -> None:
        order_id, _ = await self.setup_order(locations, units, carts, checkout, deliver, painted)
        context = {"order_id": str(order_id)}
        first, second = (await allocation.pick_list(order_id)).items
        answer = await scan(scans, staff, str(first.unit_code), ScanMode.PICK, context=context)
        assert (answer["message"], answer["progress"]) == ("picked", {"picked": 1, "total": 2})
        assert answer["next_expected"]["unit_code"] == second.unit_code  # type: ignore[index,call-overload]
        repeat = await scan(scans, staff, str(first.unit_code), ScanMode.PICK, context=context)
        assert repeat["message"] == "already_picked"
        done = await scan(scans, staff, str(second.unit_code), ScanMode.PICK, context=context)
        assert (done["progress"], done["next_expected"]) == ({"picked": 2, "total": 2}, None)

    async def test_any_free_unit_of_the_article_will_do(
        self,
        locations: LocationService,
        units: UnitService,
        carts: CartService,
        checkout: CheckoutService,
        allocation: AllocationService,
        scans: ScanService,
        deliver: Deliver,
        painted: UUID,
        staff: UUID,
    ) -> None:
        order_id, codes = await self.setup_order(
            locations, units, carts, checkout, deliver, painted, quantity=1
        )
        (item,) = (await allocation.pick_list(order_id)).items
        spare = next(code for code in codes if code != item.unit_code)
        answer = await scan(scans, staff, spare, ScanMode.PICK, context={"order_id": str(order_id)})
        assert (answer["message"], answer["effect"]["released_unit"]) == (  # type: ignore[index,call-overload]
            "picked",
            item.unit_code,
        )
        assert (await units.details(str(item.unit_code))).view.unit.status is UnitStatus.IN_STOCK

        # Undo puts everything back as it was.
        await scans.undo(UUID(str(answer["scan_id"])), staff_id=staff)
        assert (await units.details(str(item.unit_code))).view.unit.status is UnitStatus.ALLOCATED
        assert (await units.details(spare)).view.unit.status is UnitStatus.IN_STOCK

    async def test_the_articles_ean_picks_the_reserved_unit(
        self,
        locations: LocationService,
        units: UnitService,
        carts: CartService,
        checkout: CheckoutService,
        allocation: AllocationService,
        scans: ScanService,
        deliver: Deliver,
        product: ProductDetails,
        painted: UUID,
        unpainted: UUID,
        staff: UUID,
    ) -> None:
        order_id, _ = await self.setup_order(
            locations, units, carts, checkout, deliver, painted, quantity=1
        )
        context = {"order_id": str(order_id)}
        gtins = {v.id: v.gtin for s in product.product.scales for v in s.variants}
        picked = await scan(scans, staff, gtins[painted], ScanMode.PICK, context=context)
        (item,) = (await allocation.pick_list(order_id)).items
        assert (picked["message"], picked["unit"]["code"]) == ("picked", item.unit_code)  # type: ignore[index,call-overload]
        complete = await scan(scans, staff, gtins[painted], ScanMode.PICK, context=context)
        assert complete["message"] == "variant_complete"
        wrong = await scan(scans, staff, gtins[unpainted], ScanMode.PICK, context=context)
        assert wrong["message"] == "not_in_order"

    async def test_wrong_articles_and_units_are_refused(
        self,
        locations: LocationService,
        units: UnitService,
        carts: CartService,
        checkout: CheckoutService,
        allocation: AllocationService,
        scans: ScanService,
        deliver: Deliver,
        painted: UUID,
        unpainted: UUID,
        staff: UUID,
    ) -> None:
        order_id, _ = await self.setup_order(
            locations, units, carts, checkout, deliver, painted, quantity=1
        )
        other_id, _ = await self.setup_order(
            locations, units, carts, checkout, deliver, painted, quantity=1
        )
        context = {"order_id": str(order_id)}
        (others,) = (await allocation.pick_list(other_id)).items
        (wrong,) = await stock_up(locations, units, unpainted)
        (loose,) = await units.label_units(
            variant_id=painted, quantity=1, location_code=None, staff_id=None
        )
        answers = [
            await scan(scans, staff, str(others.unit_code), ScanMode.PICK, context=context),
            await scan(scans, staff, wrong, ScanMode.PICK, context=context),
            await scan(scans, staff, loose.unit.code, ScanMode.PICK, context=context),
            await scan(scans, staff, COMPARTMENT, ScanMode.PICK, context=context),
            await scan(scans, staff, wrong, ScanMode.PICK, context={"order_id": "kaputt"}),
            await scan(scans, staff, wrong, ScanMode.PICK, context={"order_id": str(uuid4())}),
        ]
        assert [a["message"] for a in answers] == [
            "reserved_for_other_order",
            "not_in_order",
            "unit_not_stored",
            "scan_unit_label",
            "order_unknown",
            "order_unknown",
        ]
        assert all(a["outcome"] == "rejected" for a in answers)

    async def test_unpaid_orders_are_not_picked(
        self,
        locations: LocationService,
        units: UnitService,
        carts: CartService,
        checkout: CheckoutService,
        scans: ScanService,
        painted: UUID,
        staff: UUID,
    ) -> None:
        (code,) = await stock_up(locations, units, painted)
        unpaid = await order(carts, checkout, (painted, 1), pay=False)
        answer = await scan(scans, staff, code, ScanMode.PICK, context={"order_id": str(unpaid)})
        assert answer["message"] == "order_not_pickable"


class TestScanRecords:
    async def test_a_repeated_scan_is_answered_without_booking_again(
        self,
        locations: LocationService,
        units: UnitService,
        scans: ScanService,
        engine: AsyncEngine,
        painted: UUID,
        staff: UUID,
    ) -> None:
        await store(locations)
        (view,) = await units.label_units(
            variant_id=painted, quantity=1, location_code=None, staff_id=None
        )
        scan_id = uuid4()
        context = {"location_code": COMPARTMENT}
        first = await scan(
            scans, staff, view.unit.code, ScanMode.PUT_AWAY, context=context, scan_id=scan_id
        )
        booked = await journal_size(engine)
        repeat = await scan(
            scans, staff, view.unit.code, ScanMode.PUT_AWAY, context=context, scan_id=scan_id
        )
        assert repeat == first
        assert await journal_size(engine) == booked
        with pytest.raises(ScanIdReusedError):
            await scan(scans, staff, "R01", ScanMode.PUT_AWAY, context=context, scan_id=scan_id)

    async def test_undo_books_backwards_once_and_only_for_a_while(
        self,
        locations: LocationService,
        units: UnitService,
        scans: ScanService,
        clock: FixedClock,
        painted: UUID,
        staff: UUID,
    ) -> None:
        await store(locations)
        await locations.create(
            parent_code="R01", segment="F02", kind=LocationKind.COMPARTMENT, name=""
        )
        first, second = await units.label_units(
            variant_id=painted, quantity=2, location_code=None, staff_id=None
        )
        context = {"location_code": COMPARTMENT}
        stored = await scan(scans, staff, first.unit.code, ScanMode.PUT_AWAY, context=context)
        undone = await scans.undo(UUID(str(stored["scan_id"])), staff_id=staff)
        assert (undone["undone"], undone["undoable"]) == (True, False)
        assert (await units.details(first.unit.code)).view.unit.status is UnitStatus.LABELED
        with pytest.raises(ScanNotUndoableError, match="already_undone"):
            await scans.undo(UUID(str(stored["scan_id"])), staff_id=staff)

        old = await scan(scans, staff, second.unit.code, ScanMode.PUT_AWAY, context=context)
        clock.advance(timedelta(seconds=UNDO_WINDOW_SECONDS + 1))
        with pytest.raises(ScanNotUndoableError, match="too_old"):
            await scans.undo(UUID(str(old["scan_id"])), staff_id=staff)

        moved = await scan(scans, staff, first.unit.code, ScanMode.PUT_AWAY, context=context)
        await scan(
            scans, staff, first.unit.code, ScanMode.PUT_AWAY, context={"location_code": "R01-F02"}
        )
        with pytest.raises(ScanNotUndoableError, match="changed_since"):
            await scans.undo(UUID(str(moved["scan_id"])), staff_id=staff)

        lookup = await scan(scans, staff, COMPARTMENT, ScanMode.LOOKUP)
        with pytest.raises(ScanNotUndoableError, match="nothing_booked"):
            await scans.undo(UUID(str(lookup["scan_id"])), staff_id=staff)
        with pytest.raises(ScanNotFoundError):
            await scans.undo(uuid4(), staff_id=staff)


class TestAvailability:
    async def test_stock_then_made_to_order_decide(
        self,
        locations: LocationService,
        units: UnitService,
        catalog: CatalogService,
        availability: AvailabilityService,
        product: ProductDetails,
        painted: UUID,
        unpainted: UUID,
    ) -> None:
        await stock_up(locations, units, painted, quantity=2)
        await catalog.change_variant(
            unpainted, expected_version=None, allow_backorder=True, lead_time_weeks=(6, 8)
        )
        found = {a.variant_id: a for a in await availability.for_product(product.product.slug)}
        assert (found[painted].availability, found[painted].free_units) == (
            Availability.IN_STOCK,
            2,
        )
        assert (found[unpainted].availability, found[unpainted].lead_time_weeks) == (
            Availability.MADE_TO_ORDER,
            (6, 8),
        )
        await catalog.change_variant(unpainted, expected_version=None, allow_backorder=False)
        found = {a.variant_id: a for a in await availability.for_product(product.product.slug)}
        assert found[unpainted].availability is Availability.UNAVAILABLE
        with pytest.raises(ProductNotFoundError):
            await availability.for_product("gibt-es-nicht")

    async def test_the_cart_takes_no_more_than_the_shelves_hold(
        self,
        locations: LocationService,
        units: UnitService,
        carts: CartService,
        checkout: CheckoutService,
        deliver: Deliver,
        painted: UUID,
    ) -> None:
        with pytest.raises(InsufficientStockError):
            await filled_cart(carts, (painted, 1))
        await stock_up(locations, units, painted, quantity=1)
        cart = await filled_cart(carts, (painted, 1))
        view = await carts.view(cart)
        assert (view.items[0].availability, view.ready_for_checkout) == (
            Availability.IN_STOCK,
            True,
        )
        with pytest.raises(InsufficientStockError):
            await carts.set_quantity(cart, painted, 2)
        # Somebody else bought the last piece in the meantime (and the worker allocated it).
        await order(carts, checkout, (painted, 1))
        await deliver()
        assert not (await carts.view(cart)).ready_for_checkout
        with pytest.raises(InsufficientStockError):
            await place(checkout, carts, cart)
        # Taking it out always works.
        assert (await carts.set_quantity(cart, painted, 0)).items == []


class TestCatalogueConsequences:
    async def test_a_variant_with_units_cannot_be_removed(
        self, locations: LocationService, units: UnitService, catalog: CatalogService, painted: UUID
    ) -> None:
        await stock_up(locations, units, painted)
        with pytest.raises(VariantHasUnitsError):
            await catalog.remove_variant(painted, expected_version=None)
