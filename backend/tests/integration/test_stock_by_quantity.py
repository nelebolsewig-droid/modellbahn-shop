"""Stock by quantity (ADR 0028) against a real PostgreSQL: shelves with Böden in one step,
what lies where, and moving, taking out and counting pieces by number."""

from uuid import UUID, uuid4

import pytest

from modellbahn.modules.catalog.application.services import CatalogService, ProductDetails
from modellbahn.modules.identity.application.services import IdentityService
from modellbahn.modules.inventory.application.allocation import AllocationService, PieceState
from modellbahn.modules.inventory.application.locations import LocationService
from modellbahn.modules.inventory.application.stock import CountLine, StockService
from modellbahn.modules.inventory.application.units import UnitService
from modellbahn.modules.inventory.domain.errors import (
    CountOutdatedError,
    CountTakesReservedError,
    InvalidFieldError,
    LocationNotEmptyError,
    NotEnoughFreeError,
    NotEnoughPiecesError,
    ProductNotFoundError,
)
from modellbahn.modules.inventory.domain.model import (
    LocationKind,
    MovementReason,
    ScrapReason,
    UnitStatus,
)
from modellbahn.modules.media.application.services import MediaService
from modellbahn.modules.sales.application.cart import CartService
from modellbahn.modules.sales.application.checkout import CheckoutService
from tests.conftest import Deliver
from tests.inventory_support import staff_member
from tests.media_support import InMemoryMediaStorage
from tests.sales_support import filled_cart, place, shop_product, variant_id

pytestmark = pytest.mark.usefixtures("clean_database")

TOP = "R01-B01"
BOTTOM = "R01-B02"


@pytest.fixture
async def product(
    catalog: CatalogService,
    media: MediaService,
    media_storage: InMemoryMediaStorage,
    deliver: Deliver,
) -> ProductDetails:
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
async def shelf(locations: LocationService) -> None:
    await locations.create_shelf(name="Regal 1", levels=2)


async def book_in(units: UnitService, variant: UUID, quantity: int, code: str) -> None:
    await units.label_units(
        variant_id=variant, quantity=quantity, location_code=code, staff_id=None
    )


async def paid_order(carts: CartService, checkout: CheckoutService, variant: UUID, n: int) -> UUID:
    cart = await filled_cart(carts, (variant, n))
    placed = (await place(checkout, carts, cart)).details.order
    await checkout.pay(public_token=placed.public_token, method="succeeds", idempotency_key=uuid4())
    return placed.id


async def here(stock: StockService, code: str) -> dict[UUID, tuple[int, int]]:
    """``variant → (free, reserved)`` in the place."""
    return {
        line.variant_id: (line.free, line.reserved)
        for line in await stock.places(location_code=code)
    }


class TestShelves:
    async def test_a_shelf_with_its_boeden_in_one_step(self, locations: LocationService) -> None:
        first = await locations.create_shelf(name="Regal am Fenster", levels=3)
        second = await locations.create_shelf(name="  ", levels=0)

        assert (first.shelf.code, first.shelf.name) == ("R01", "Regal am Fenster")
        assert [(b.code, b.name) for b in first.levels] == [
            ("R01-B01", "Boden 1"),
            ("R01-B02", "Boden 2"),
            ("R01-B03", "Boden 3"),
        ]
        assert (second.shelf.code, second.shelf.name, second.levels) == ("R02", "Regal 2", [])
        tree = {node.location.code: node for node in await locations.tree()}
        # The site was made on the way, once.
        assert [code for code, node in tree.items() if node.location.kind is LocationKind.SITE] == [
            "LAGER"
        ]
        assert tree["R01-B02"].place == "Regal am Fenster, Boden 2"
        # A shelf with Böden holds no goods itself; one without does.
        assert (tree["R01"].takes_goods, tree["R02"].takes_goods) == (False, True)
        assert tree["R01-B01"].takes_goods

    async def test_goods_on_a_shelf_without_boeden_and_the_limits(
        self, locations: LocationService, units: UnitService, painted: UUID
    ) -> None:
        await locations.create_shelf(name="Regal 1", levels=1)
        await locations.create_shelf(name="Regal 2", levels=0)
        await book_in(units, painted, 1, "R02")
        with pytest.raises(InvalidFieldError, match="holds no goods"):
            await book_in(units, painted, 1, "R01")
        # A Boden below goods would leave them lying nowhere.
        with pytest.raises(LocationNotEmptyError):
            await locations.create(
                parent_code="R02", segment="B01", kind=LocationKind.COMPARTMENT, name=""
            )
        with pytest.raises(InvalidFieldError, match="levels"):
            await locations.create_shelf(name="", levels=21)


class TestWhatLiesWhere:
    async def test_per_place_and_per_model(
        self,
        units: UnitService,
        stock: StockService,
        carts: CartService,
        checkout: CheckoutService,
        catalog: CatalogService,
        deliver: Deliver,
        shelf: None,
        product: ProductDetails,
        painted: UUID,
        unpainted: UUID,
    ) -> None:
        await book_in(units, painted, 3, TOP)
        await book_in(units, painted, 2, BOTTOM)
        await book_in(units, unpainted, 1, BOTTOM)
        await units.label_units(variant_id=painted, quantity=1, location_code=None, staff_id=None)
        await paid_order(carts, checkout, painted, 1)
        await catalog.change_variant(unpainted, expected_version=None, allow_backorder=True)
        await paid_order(carts, checkout, unpainted, 2)
        await deliver()

        lines = await stock.places(product_id=product.product.id)
        assert [line.place for line in lines] == ["Regal 1, Boden 1"] + ["Regal 1, Boden 2"] * 2
        assert {(line.place, line.variant_id, line.free, line.reserved) for line in lines} == {
            ("Regal 1, Boden 1", painted, 2, 1),
            ("Regal 1, Boden 2", painted, 2, 0),
            ("Regal 1, Boden 2", unpainted, 0, 1),
        }
        (summary,) = await stock.products()
        assert (summary.product_id, summary.free, summary.reserved) == (product.product.id, 4, 2)
        assert (summary.labeled, summary.backordered) == (1, 1)
        assert [(p.place, p.quantity) for p in summary.places] == [
            ("Regal 1, Boden 1", 3),
            ("Regal 1, Boden 2", 3),
        ]
        assert await stock.places(location_code="R77") == []


class TestMoving:
    async def test_a_number_from_one_place_to_another_reserved_ones_keep_their_order(
        self,
        units: UnitService,
        stock: StockService,
        carts: CartService,
        checkout: CheckoutService,
        allocation: AllocationService,
        deliver: Deliver,
        shelf: None,
        painted: UUID,
        staff: UUID,
    ) -> None:
        await book_in(units, painted, 3, TOP)
        order_id = await paid_order(carts, checkout, painted, 1)
        await deliver()

        moved = await stock.move(painted, from_code=TOP, to_code=BOTTOM, quantity=3, staff_id=staff)

        assert (moved.moved, moved.target.code) == (3, BOTTOM)
        assert await here(stock, BOTTOM) == {painted: (2, 1)}
        (item,) = (await allocation.pick_list(order_id)).items
        assert item.state is PieceState.RESERVED
        assert item.location is not None
        assert item.location.code == BOTTOM

    async def test_fewer_there_moves_nothing(
        self, units: UnitService, stock: StockService, shelf: None, painted: UUID, staff: UUID
    ) -> None:
        await book_in(units, painted, 2, TOP)
        with pytest.raises(NotEnoughPiecesError) as error:
            await stock.move(painted, from_code=TOP, to_code=BOTTOM, quantity=3, staff_id=staff)
        assert error.value.available == 2
        assert await here(stock, BOTTOM) == {}
        with pytest.raises(InvalidFieldError, match="same place"):
            await stock.move(painted, from_code=TOP, to_code=TOP, quantity=1, staff_id=staff)


class TestTakingOut:
    async def test_free_pieces_with_a_reason_from_a_place_or_anywhere(
        self,
        units: UnitService,
        stock: StockService,
        carts: CartService,
        checkout: CheckoutService,
        deliver: Deliver,
        shelf: None,
        painted: UUID,
        staff: UUID,
    ) -> None:
        await book_in(units, painted, 2, TOP)
        await book_in(units, painted, 2, BOTTOM)
        await paid_order(carts, checkout, painted, 1)
        await deliver()

        with pytest.raises(NotEnoughFreeError) as error:
            await stock.scrap(
                painted,
                location_code=TOP,
                quantity=2,
                reason=ScrapReason.SOLD,
                note="",
                staff_id=staff,
            )
        assert error.value.available == 1
        out = await stock.scrap(
            painted,
            location_code=None,
            quantity=3,
            reason=ScrapReason.SOLD,
            note="Messe",
            staff_id=staff,
        )

        assert out.scrapped == 3
        assert sum(source.quantity for source in out.sources) == 3
        assert await here(stock, TOP) == {painted: (0, 1)}
        scrapped = (await units.list_units(painted, statuses={UnitStatus.SCRAPPED})).views
        assert {(v.unit.scrap_reason, v.unit.scrap_note) for v in scrapped} == {
            (ScrapReason.SOLD, "Messe")
        }


class TestCounting:
    async def test_missing_out_extra_in_and_a_waiting_order_served(
        self,
        units: UnitService,
        stock: StockService,
        catalog: CatalogService,
        carts: CartService,
        checkout: CheckoutService,
        allocation: AllocationService,
        deliver: Deliver,
        shelf: None,
        painted: UUID,
        unpainted: UUID,
        staff: UUID,
    ) -> None:
        await book_in(units, painted, 4, TOP)
        await catalog.change_variant(unpainted, expected_version=None, allow_backorder=True)
        waiting = await paid_order(carts, checkout, unpainted, 1)
        await deliver()

        result = await stock.count(
            [
                CountLine(variant_id=painted, location_code=TOP, expected=4, counted=1),
                CountLine(variant_id=unpainted, location_code="r01-b02", expected=0, counted=3),
            ],
            staff_id=staff,
        )

        assert (result.missing, result.added, result.reserved) == (3, 3, 1)
        assert await here(stock, TOP) == {painted: (1, 0)}
        assert await here(stock, BOTTOM) == {unpainted: (2, 1)}
        missing = (await units.list_units(painted, statuses={UnitStatus.SCRAPPED})).views
        assert {(v.unit.scrap_reason, v.unit.scrap_note) for v in missing} == {
            (ScrapReason.MISSING, f"Gezählt {TOP}")
        }
        assert [i.state for i in (await allocation.pick_list(waiting)).items] == [
            PieceState.RESERVED
        ]

    async def test_a_changed_place_or_reserved_pieces_book_nothing_at_all(
        self,
        units: UnitService,
        stock: StockService,
        carts: CartService,
        checkout: CheckoutService,
        deliver: Deliver,
        shelf: None,
        painted: UUID,
        unpainted: UUID,
        staff: UUID,
    ) -> None:
        await book_in(units, painted, 2, TOP)
        await book_in(units, unpainted, 1, BOTTOM)
        await paid_order(carts, checkout, painted, 2)
        await deliver()
        fine = CountLine(variant_id=unpainted, location_code=BOTTOM, expected=1, counted=0)

        with pytest.raises(CountTakesReservedError) as reserved:
            await stock.count(
                [fine, CountLine(variant_id=painted, location_code=TOP, expected=2, counted=1)],
                staff_id=staff,
            )
        assert reserved.value.lines == [f"{(await here_sku(stock, TOP))} in {TOP}"]
        with pytest.raises(CountOutdatedError):
            await stock.count(
                [fine, CountLine(variant_id=painted, location_code=TOP, expected=1, counted=2)],
                staff_id=staff,
            )
        # All or nothing: the fine line was not booked either.
        assert await here(stock, BOTTOM) == {unpainted: (1, 0)}
        with pytest.raises(InvalidFieldError, match="twice"):
            await stock.count([fine, fine], staff_id=staff)


async def here_sku(stock: StockService, code: str) -> str:
    (line,) = await stock.places(location_code=code)
    assert line.variant is not None
    return line.variant.sku


class TestHistory:
    async def test_bookings_grouped_newest_first(
        self,
        units: UnitService,
        stock: StockService,
        shelf: None,
        product: ProductDetails,
        painted: UUID,
        staff: UUID,
    ) -> None:
        await book_in(units, painted, 3, TOP)
        await stock.move(painted, from_code=TOP, to_code=BOTTOM, quantity=2, staff_id=staff)

        rows = await stock.history(product.product.id)

        assert [(r.reason, r.quantity, r.from_place, r.to_place) for r in rows] == [
            (MovementReason.MOVE, 2, "Regal 1, Boden 1", "Regal 1, Boden 2"),
            (MovementReason.PUT_AWAY, 3, None, "Regal 1, Boden 1"),
            (MovementReason.LABEL, 3, None, None),
        ]
        assert rows[0].staff_name == "Lagerist"
        with pytest.raises(ProductNotFoundError):
            await stock.history(uuid4())
