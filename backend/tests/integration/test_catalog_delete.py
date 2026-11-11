"""Deleting a test model: what goes along, and what holds a product back.

A product leaves the shop first (archived). Its pieces that never left the shop go with
it, journal and all; open orders (eBay orders on their way in too), sold pieces and eBay
listings that eBay still shows hold it back. Orders that are done keep their own copy and
do not.
"""

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, insert, select, update
from sqlalchemy.ext.asyncio import AsyncEngine

from modellbahn.modules.catalog.application.services import CatalogService, ProductDetails
from modellbahn.modules.catalog.domain.errors import (
    ProductHasHistoryError,
    ProductInOpenOrdersError,
    ProductNotDeletableError,
    ProductNotFoundError,
    ProductOnMarketplaceError,
)
from modellbahn.modules.identity.application.services import IdentityService
from modellbahn.modules.inventory.application.allocation import AllocationService
from modellbahn.modules.inventory.application.locations import LocationService
from modellbahn.modules.inventory.application.scanning import ScanService
from modellbahn.modules.inventory.application.units import UnitService
from modellbahn.modules.inventory.domain.model import ScanMode
from modellbahn.modules.inventory.infrastructure.tables import stock_ledger
from modellbahn.modules.inventory.infrastructure.tables import units as unit_rows
from modellbahn.modules.marketplace.infrastructure.tables import (
    listings,
    marketplace_order_lines,
    marketplace_orders,
)
from modellbahn.modules.media.application.services import MediaService
from modellbahn.modules.sales.application.cart import CartService
from modellbahn.modules.sales.application.checkout import CheckoutService
from modellbahn.modules.sales.application.orders import OrderService
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

NOW = datetime(2026, 11, 11, 10, 0, tzinfo=UTC)


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


async def count(engine: AsyncEngine, table: object, **where: object) -> int:
    query = select(func.count()).select_from(table)  # type: ignore[arg-type]
    for column, value in where.items():
        query = query.where(getattr(table, "c")[column] == value)  # noqa: B009
    async with engine.connect() as connection:
        return int((await connection.execute(query)).scalar_one())


async def paid_order(carts: CartService, checkout: CheckoutService, variant: UUID) -> UUID:
    cart = await filled_cart(carts, (variant, 1))
    order = (await place(checkout, carts, cart)).details.order
    await checkout.pay(public_token=order.public_token, method="succeeds", idempotency_key=uuid4())
    return order.id


async def listing(
    engine: AsyncEngine, product_id: UUID, *, status: str, external_id: str = ""
) -> UUID:
    listing_id = uuid4()
    async with engine.begin() as connection:
        await connection.execute(
            insert(listings).values(
                id=listing_id,
                product_id=product_id,
                scale_code="H0",
                group_key=f"MB-{uuid4().hex[:8]}",
                wanted=True,
                status=status,
                external_id=external_id,
                needs_sync=False,
                error_code="not_in_shop" if status == "failed" else None,
                created_at=NOW,
                updated_at=NOW,
            )
        )
    return listing_id


async def ebay_order(engine: AsyncEngine, variant: UUID, external_id: str) -> UUID:
    """A paid eBay order as the marketplace received it; the shop's order follows later."""
    marketplace_order_id = uuid4()
    async with engine.begin() as connection:
        await connection.execute(
            insert(marketplace_orders).values(
                id=marketplace_order_id,
                channel="ebay",
                external_id=external_id,
                order_id=uuid4(),
                status="received",
                buyer_name="kaeufer",
                email="kaeufer@example.com",
                recipient="Erika Mustermann",
                street="Bahnhofstraße 1",
                postal_code="17235",
                city="Neustrelitz",
                country_code="DE",
                shipping_cents=590,
                total_cents=5490,
                paid_at=NOW,
                received_at=NOW,
                updated_at=NOW,
            )
        )
        await connection.execute(
            insert(marketplace_order_lines).values(
                id=uuid4(),
                marketplace_order_id=marketplace_order_id,
                position=1,
                line_ref="10001",
                sku="TEST",
                variant_id=variant,
                title="Testmodell",
                quantity=1,
                unit_price_cents=4900,
            )
        )
    return marketplace_order_id


class TestDeleting:
    async def test_a_test_model_goes_with_its_pieces(
        self,
        catalog: CatalogService,
        locations: LocationService,
        units: UnitService,
        engine: AsyncEngine,
        product: ProductDetails,
        painted: UUID,
    ) -> None:
        product_id = product.product.id
        await units.label_units(
            variant_id=painted, quantity=2, location_code=await store(locations), staff_id=None
        )
        await units.label_units(variant_id=painted, quantity=1, location_code=None, staff_id=None)
        assert await count(engine, unit_rows, variant_id=painted) == 3

        # In the shop it is archived first.
        with pytest.raises(ProductNotDeletableError):
            await catalog.delete_product(product_id, expected_version=None)
        await catalog.archive(product_id, expected_version=None)
        await catalog.delete_product(product_id, expected_version=None)

        with pytest.raises(ProductNotFoundError):
            await catalog.get_product(product_id)
        assert await count(engine, unit_rows, variant_id=painted) == 0
        assert await count(engine, stock_ledger) == 0

    async def test_open_orders_hold_it_back(
        self,
        catalog: CatalogService,
        carts: CartService,
        checkout: CheckoutService,
        orders: OrderService,
        locations: LocationService,
        units: UnitService,
        deliver: Deliver,
        product: ProductDetails,
        painted: UUID,
    ) -> None:
        await stock_up(locations, units, painted)
        order_id = await paid_order(carts, checkout, painted)
        await deliver()  # the piece is reserved for the order
        await catalog.archive(product.product.id, expected_version=None)
        with pytest.raises(ProductInOpenOrdersError) as held:
            await catalog.delete_product(product.product.id, expected_version=None)
        assert held.value.numbers[0].startswith("MB-")
        # Cancelled, the order keeps its own copy and lets the product go.
        await orders.cancel(order_id, note="")
        await deliver()  # the reserved piece goes back on the shelf
        await catalog.delete_product(product.product.id, expected_version=None)

    async def test_sold_pieces_hold_it_back(
        self,
        catalog: CatalogService,
        carts: CartService,
        checkout: CheckoutService,
        orders: OrderService,
        identity: IdentityService,
        locations: LocationService,
        units: UnitService,
        scans: ScanService,
        allocation: AllocationService,
        deliver: Deliver,
        product: ProductDetails,
        painted: UUID,
    ) -> None:
        await stock_up(locations, units, painted)
        order_id = await paid_order(carts, checkout, painted)
        await deliver()
        await pick_everything(scans, allocation, order_id, await staff_member(identity))
        await orders.ship(order_id, carrier="DHL", tracking_number="00340434")
        await catalog.archive(product.product.id, expected_version=None)
        with pytest.raises(ProductHasHistoryError) as held:
            await catalog.delete_product(product.product.id, expected_version=None)
        assert held.value.pieces == 1

    async def test_undone_scans_go_along(
        self,
        catalog: CatalogService,
        identity: IdentityService,
        locations: LocationService,
        units: UnitService,
        scans: ScanService,
        engine: AsyncEngine,
        product: ProductDetails,
        painted: UUID,
    ) -> None:
        staff = await staff_member(identity)
        await store(locations)
        (piece,) = await units.label_units(
            variant_id=painted, quantity=1, location_code=None, staff_id=None
        )
        context = {"location_code": COMPARTMENT}
        stored = await scan(scans, staff, piece.unit.code, ScanMode.PUT_AWAY, context=context)
        await scans.undo(UUID(str(stored["scan_id"])), staff_id=staff)
        await scan(scans, staff, piece.unit.code, ScanMode.PUT_AWAY, context=context)

        await catalog.archive(product.product.id, expected_version=None)
        await catalog.delete_product(product.product.id, expected_version=None)
        assert await count(engine, unit_rows, variant_id=painted) == 0
        assert await count(engine, stock_ledger) == 0

    async def test_a_listing_ebay_still_shows_holds_it_back_until_it_ended(
        self,
        catalog: CatalogService,
        engine: AsyncEngine,
        product: ProductDetails,
    ) -> None:
        product_id = product.product.id
        up = await listing(engine, product_id, status="active", external_id="ebay-group-1")
        await catalog.archive(product_id, expected_version=None)
        with pytest.raises(ProductOnMarketplaceError):
            await catalog.delete_product(product_id, expected_version=None)
        async with engine.begin() as connection:
            await connection.execute(
                update(listings).where(listings.c.id == up).values(status="ended")
            )
        await catalog.delete_product(product_id, expected_version=None)
        assert await count(engine, listings) == 0

    async def test_a_listing_held_back_from_ebay_goes_along(
        self,
        catalog: CatalogService,
        engine: AsyncEngine,
        product: ProductDetails,
    ) -> None:
        # Archived, the sync keeps the listing off eBay: failed, without an eBay id.
        await listing(engine, product.product.id, status="failed")
        await catalog.archive(product.product.id, expected_version=None)
        await catalog.delete_product(product.product.id, expected_version=None)
        assert await count(engine, listings) == 0

    async def test_an_ebay_order_on_its_way_in_holds_it_back(
        self,
        catalog: CatalogService,
        engine: AsyncEngine,
        product: ProductDetails,
        painted: UUID,
    ) -> None:
        received = await ebay_order(engine, painted, "12-34567-89012")
        await catalog.archive(product.product.id, expected_version=None)
        with pytest.raises(ProductInOpenOrdersError) as held:
            await catalog.delete_product(product.product.id, expected_version=None)
        assert held.value.numbers == ["eBay 12-34567-89012"]
        # Cancelled on eBay, it no longer needs the article.
        async with engine.begin() as connection:
            await connection.execute(
                update(marketplace_orders)
                .where(marketplace_orders.c.id == received)
                .values(status="cancelled")
            )
        await catalog.delete_product(product.product.id, expected_version=None)
