"""eBay on the built-in test marketplace: connecting, offers in step with the shop, orders.

The whole chain runs as in production, only the gateway is the test marketplace: an
offer goes up, a buyer buys, the sale becomes a paid shop order, the workshop picks and
ships it, and the tracking number goes back.
"""

import json
from urllib.parse import parse_qs, urlsplit
from uuid import UUID, uuid4

import pytest
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from modellbahn.modules.catalog.application.services import CatalogService, ProductDetails
from modellbahn.modules.identity.application.services import IdentityService
from modellbahn.modules.inventory.application.allocation import AllocationService
from modellbahn.modules.inventory.application.locations import LocationService
from modellbahn.modules.inventory.application.scanning import ScanService
from modellbahn.modules.inventory.application.units import UnitService
from modellbahn.modules.marketplace.application.connection import SettingsChange
from modellbahn.modules.marketplace.application.deletions import (
    ACCOUNT_DELETION_TOPIC,
    AccountDeletionService,
    DeletionOutcome,
    DeletionReceipt,
)
from modellbahn.modules.marketplace.application.marketplace import Marketplace
from modellbahn.modules.marketplace.domain.errors import (
    AccountNotReadyError,
    ConnectionStateInvalidError,
    DeletionsUnverifiableError,
    ListingNotFoundError,
    NotificationInvalidError,
    NotificationSignatureError,
)
from modellbahn.modules.marketplace.domain.model import (
    EBAY,
    Blocker,
    ConnectionStatus,
    Listing,
    ListingStatus,
    MarketplaceOrder,
    MarketplaceOrderStatus,
    ReceivedLine,
)
from modellbahn.modules.marketplace.infrastructure.builtin import (
    CONSENT_CODE,
    SELLER_NAME,
    TEST_BUYER_NAME,
    sign_test_notification,
)
from modellbahn.modules.marketplace.infrastructure.setup import build_account_deletions
from modellbahn.modules.media.application.services import MediaService
from modellbahn.modules.sales.application.orders import OrderService
from modellbahn.modules.sales.domain.errors import MarketplaceOrderError
from modellbahn.modules.sales.domain.model import CancelReason, OrderStatus, SalesChannel
from modellbahn.platform.clock import FixedClock
from modellbahn.platform.config import Settings
from modellbahn.platform.mail import InMemoryMailer
from tests.conftest import Deliver
from tests.inventory_support import pick_everything, staff_member, stock_up
from tests.media_support import InMemoryMediaStorage
from tests.sales_support import shop_product, variant_id

pytestmark = pytest.mark.usefixtures("clean_database")

EBAY_CATEGORY = "180250"


async def connect(marketplace: Marketplace) -> None:
    """Connect on the test marketplace and choose the one policy left open."""
    url = await marketplace.connection.begin_connect()
    query = parse_qs(urlsplit(url).query)
    await marketplace.connection.complete_connect(code=query["code"][0], state=query["state"][0])
    await marketplace.connection.change_settings(
        SettingsChange(fulfillment_policy_id="test-ship-dhl")
    )


async def offered_product(
    marketplace: Marketplace,
    catalog: CatalogService,
    media: MediaService,
    media_storage: InMemoryMediaStorage,
    deliver: Deliver,
    *,
    made_to_order: bool = True,
) -> ProductDetails:
    """A shop product in H0 (kit and finished model) with its category mapped to eBay."""
    details = await shop_product(
        catalog, media, media_storage, deliver, made_to_order=made_to_order
    )
    category_id = details.product.primary_category_id
    assert category_id is not None
    await marketplace.connection.set_category_map({category_id: EBAY_CATEGORY})
    return details


async def synced(marketplace: Marketplace, product_id: UUID) -> Listing:
    await marketplace.listings.sync_due()
    (listing,) = await marketplace.listings.of_product(product_id)
    return listing


class TestConnection:
    async def test_connecting_on_the_test_marketplace(self, marketplace: Marketplace) -> None:
        url = await marketplace.connection.begin_connect()
        assert url.startswith("https://shop.test/api/v1/admin/marketplace/ebay/callback?")
        state = parse_qs(urlsplit(url).query)["state"][0]

        account = await marketplace.connection.complete_connect(code=CONSENT_CODE, state=state)

        assert account.status is ConnectionStatus.CONNECTED
        assert account.seller_name == SELLER_NAME
        assert account.location_ready
        # The only payment and return policy are chosen; of two shipping policies, none.
        assert account.payment_policy_id == "test-pay"
        assert account.return_policy_id == "test-return-30"
        assert account.blockers == [Blocker.NO_FULFILLMENT_POLICY]
        # The tokens are sealed in the database.
        assert account.refresh_token not in {"", "test-refresh"}

    async def test_an_answer_is_used_once(self, marketplace: Marketplace) -> None:
        url = await marketplace.connection.begin_connect()
        state = parse_qs(urlsplit(url).query)["state"][0]
        await marketplace.connection.complete_connect(code=CONSENT_CODE, state=state)
        with pytest.raises(ConnectionStateInvalidError):
            await marketplace.connection.complete_connect(code=CONSENT_CODE, state=state)

    async def test_a_foreign_answer_connects_nothing(self, marketplace: Marketplace) -> None:
        await marketplace.connection.begin_connect()
        with pytest.raises(ConnectionStateInvalidError):
            await marketplace.connection.complete_connect(code=CONSENT_CODE, state="geraten")
        assert (await marketplace.connection.status()).status is ConnectionStatus.DISCONNECTED

    async def test_the_category_map_follows_the_catalogue(
        self, marketplace: Marketplace, catalog: CatalogService
    ) -> None:
        trucks = await catalog.create_category(name="LKW")
        await marketplace.connection.set_category_map({trucks.id: " 180250 "})
        (mapping,) = [m for m in await marketplace.connection.category_map() if m.path == "LKW"]
        assert mapping.ebay_category_id == "180250"
        await marketplace.connection.set_category_map({trucks.id: ""})
        assert all(m.ebay_category_id == "" for m in await marketplace.connection.category_map())


class TestListings:
    async def test_a_product_goes_up_with_both_finishes(
        self,
        marketplace: Marketplace,
        catalog: CatalogService,
        media: MediaService,
        media_storage: InMemoryMediaStorage,
        deliver: Deliver,
    ) -> None:
        await connect(marketplace)
        details = await offered_product(marketplace, catalog, media, media_storage, deliver)

        wanted = await marketplace.listings.want(details.product.id, "H0", wanted=True)
        assert wanted.status is ListingStatus.PENDING
        listing = await synced(marketplace, details.product.id)

        assert listing.status is ListingStatus.ACTIVE
        assert listing.external_id.startswith("99")
        assert listing.group_key == f"MB-{details.product.number:06d}-H0"
        # Made to order: three of each may sell at once, at the shop's prices.
        assert sorted((item.quantity, item.price_cents) for item in listing.items) == [
            (3, 2990),
            (3, 4990),
        ]
        assert all(item.offer_id for item in listing.items)

    async def test_the_markup_reaches_every_offer(
        self,
        marketplace: Marketplace,
        catalog: CatalogService,
        media: MediaService,
        media_storage: InMemoryMediaStorage,
        deliver: Deliver,
    ) -> None:
        await connect(marketplace)
        details = await offered_product(marketplace, catalog, media, media_storage, deliver)
        await marketplace.listings.want(details.product.id, "H0", wanted=True)
        await synced(marketplace, details.product.id)

        await marketplace.connection.change_settings(SettingsChange(price_markup_percent=10))
        listing = await synced(marketplace, details.product.id)
        assert sorted(item.price_cents for item in listing.items) == [3289, 5489]

    async def test_without_an_ebay_category_it_waits_with_the_reason(
        self,
        marketplace: Marketplace,
        catalog: CatalogService,
        media: MediaService,
        media_storage: InMemoryMediaStorage,
        deliver: Deliver,
    ) -> None:
        await connect(marketplace)
        details = await shop_product(catalog, media, media_storage, deliver)
        await marketplace.listings.want(details.product.id, "H0", wanted=True)

        listing = await synced(marketplace, details.product.id)
        assert listing.status is ListingStatus.FAILED
        assert listing.error_code == "no_category"
        assert not listing.is_up

    async def test_sold_out_it_pauses_and_comes_back_with_stock(
        self,
        marketplace: Marketplace,
        catalog: CatalogService,
        media: MediaService,
        media_storage: InMemoryMediaStorage,
        deliver: Deliver,
        locations: LocationService,
        units: UnitService,
    ) -> None:
        await connect(marketplace)
        details = await offered_product(
            marketplace, catalog, media, media_storage, deliver, made_to_order=False
        )
        await marketplace.listings.want(details.product.id, "H0", wanted=True)
        listing = await synced(marketplace, details.product.id)
        assert listing.status is ListingStatus.ENDED
        assert listing.wanted

        await stock_up(locations, units, variant_id(details, "H0", "painted"), quantity=2)
        await deliver()  # StockChanged marks the listing due.
        listing = await synced(marketplace, details.product.id)
        assert listing.status is ListingStatus.ACTIVE
        assert sorted(item.quantity for item in listing.items) == [0, 2]

    async def test_taking_it_down(
        self,
        marketplace: Marketplace,
        catalog: CatalogService,
        media: MediaService,
        media_storage: InMemoryMediaStorage,
        deliver: Deliver,
    ) -> None:
        await connect(marketplace)
        details = await offered_product(marketplace, catalog, media, media_storage, deliver)
        await marketplace.listings.want(details.product.id, "H0", wanted=True)
        await synced(marketplace, details.product.id)

        await marketplace.listings.want(details.product.id, "H0", wanted=False)
        listing = await synced(marketplace, details.product.id)
        assert listing.status is ListingStatus.ENDED
        assert not listing.is_up

    async def test_archiving_the_product_takes_it_off_ebay(
        self,
        marketplace: Marketplace,
        catalog: CatalogService,
        media: MediaService,
        media_storage: InMemoryMediaStorage,
        deliver: Deliver,
    ) -> None:
        await connect(marketplace)
        details = await offered_product(marketplace, catalog, media, media_storage, deliver)
        await marketplace.listings.want(details.product.id, "H0", wanted=True)
        await synced(marketplace, details.product.id)

        await catalog.archive(details.product.id, expected_version=None)
        await deliver()  # ProductArchived marks it due.
        listing = await synced(marketplace, details.product.id)
        assert listing.error_code == "not_in_shop"
        assert not listing.is_up

    async def test_nothing_goes_up_before_the_account_is_ready(
        self,
        marketplace: Marketplace,
        catalog: CatalogService,
        media: MediaService,
        media_storage: InMemoryMediaStorage,
        deliver: Deliver,
    ) -> None:
        url = await marketplace.connection.begin_connect()
        state = parse_qs(urlsplit(url).query)["state"][0]
        await marketplace.connection.complete_connect(code=CONSENT_CODE, state=state)
        details = await offered_product(marketplace, catalog, media, media_storage, deliver)
        listing = await marketplace.listings.want(details.product.id, "H0", wanted=True)

        assert await marketplace.listings.sync_due() == 0
        with pytest.raises(AccountNotReadyError):
            await marketplace.listings.sync(listing.id)

    async def test_an_unknown_scale_cannot_be_offered(
        self, marketplace: Marketplace, catalog: CatalogService
    ) -> None:
        details = await catalog.create_product(name="Ohne Maßstab")
        with pytest.raises(ListingNotFoundError):
            await marketplace.listings.want(details.product.id, "H0", wanted=True)

    async def test_disconnecting_takes_every_offer_down(
        self,
        marketplace: Marketplace,
        catalog: CatalogService,
        media: MediaService,
        media_storage: InMemoryMediaStorage,
        deliver: Deliver,
    ) -> None:
        await connect(marketplace)
        details = await offered_product(marketplace, catalog, media, media_storage, deliver)
        await marketplace.listings.want(details.product.id, "H0", wanted=True)
        await synced(marketplace, details.product.id)

        account = await marketplace.connection.disconnect()
        assert account.status is ConnectionStatus.DISCONNECTED
        (listing,) = await marketplace.listings.of_product(details.product.id)
        assert listing.status is ListingStatus.ENDED
        assert listing.wanted


class TestOrders:
    async def test_a_sale_on_ebay_is_packed_and_shipped_like_a_shop_order(
        self,
        marketplace: Marketplace,
        catalog: CatalogService,
        media: MediaService,
        media_storage: InMemoryMediaStorage,
        deliver: Deliver,
        orders: OrderService,
        mailer: InMemoryMailer,
        locations: LocationService,
        units: UnitService,
        scans: ScanService,
        allocation: AllocationService,
        identity: IdentityService,
    ) -> None:
        await connect(marketplace)
        details = await offered_product(marketplace, catalog, media, media_storage, deliver)
        painted = variant_id(details, "H0", "painted")
        await stock_up(locations, units, painted)
        await marketplace.listings.want(details.product.id, "H0", wanted=True)
        listing = await synced(marketplace, details.product.id)
        sku = next(item.sku for item in listing.items if item.variant_id == painted)

        external_id = await marketplace.orders.sell_test(sku=sku, quantity=1)
        (view,) = await marketplace.orders.recent()
        assert view.order.external_id == external_id
        assert view.order.status is MarketplaceOrderStatus.RECEIVED
        assert view.order_number is None

        await deliver()  # The sales take it over ...
        await deliver()  # ... and the inventory allocates it.
        order = (await orders.get(view.order.order_id)).order
        assert order.status is OrderStatus.PAID
        assert order.channel is SalesChannel.EBAY
        assert order.external_ref == external_id
        assert order.total_cents == 4990 + 590
        assert order.payments[0].provider == "ebay"
        # The buyer hears from eBay, not from the shop.
        assert mailer.sent == []

        await pick_everything(scans, allocation, order.id, await staff_member(identity))
        await orders.ship(order.id, carrier="DHL", tracking_number="00340434161234567890")
        await deliver()
        (view,) = await marketplace.orders.recent()
        assert view.order.status is MarketplaceOrderStatus.SHIPPED
        assert view.order_number == order.number
        assert mailer.sent == []

    async def test_a_cancellation_on_ebay_cancels_the_order(
        self,
        marketplace: Marketplace,
        catalog: CatalogService,
        media: MediaService,
        media_storage: InMemoryMediaStorage,
        deliver: Deliver,
        orders: OrderService,
    ) -> None:
        await connect(marketplace)
        details = await offered_product(marketplace, catalog, media, media_storage, deliver)
        await marketplace.listings.want(details.product.id, "H0", wanted=True)
        listing = await synced(marketplace, details.product.id)
        external_id = await marketplace.orders.sell_test(sku=listing.items[0].sku, quantity=2)
        await deliver()
        (view,) = await marketplace.orders.recent()

        # The shop cannot cancel it: the buyer's money is with eBay.
        with pytest.raises(MarketplaceOrderError):
            await orders.cancel(view.order.order_id, note="")

        await marketplace.orders.cancel_test(external_id)
        await deliver()
        order = (await orders.get(view.order.order_id)).order
        assert order.status is OrderStatus.CANCELLED
        assert order.cancel_reason is CancelReason.BY_MARKETPLACE
        (view,) = await marketplace.orders.recent()
        assert view.order.status is MarketplaceOrderStatus.CANCELLED

    async def test_fetching_twice_takes_an_order_over_once(
        self,
        marketplace: Marketplace,
        catalog: CatalogService,
        media: MediaService,
        media_storage: InMemoryMediaStorage,
        deliver: Deliver,
    ) -> None:
        await connect(marketplace)
        details = await offered_product(marketplace, catalog, media, media_storage, deliver)
        await marketplace.listings.want(details.product.id, "H0", wanted=True)
        listing = await synced(marketplace, details.product.id)
        await marketplace.orders.sell_test(sku=listing.items[0].sku, quantity=1)

        # The next fetch looks back over the same sale (the overlap); it stays one order.
        assert await marketplace.orders.fetch() == 0
        await deliver()
        await deliver()
        assert len(await marketplace.orders.recent()) == 1

    async def test_only_offered_articles_can_be_bought(self, marketplace: Marketplace) -> None:
        await connect(marketplace)
        with pytest.raises(ListingNotFoundError):
            await marketplace.orders.sell_test(sku="MB-999999-H0-F", quantity=1)


@pytest.fixture
def deletions(
    settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
    marketplace: Marketplace,
    clock: FixedClock,
) -> AccountDeletionService:
    """eBay's notifications of closed accounts, signed on the test marketplace."""
    return build_account_deletions(
        settings.model_copy(update={"ebay_verification_token": SecretStr("t" * 32)}),
        session_factory,
        marketplace,
        clock,
    )


async def received(marketplace: Marketplace, buyer_name: str, clock: FixedClock) -> None:
    """An order of this buyer as eBay reported it (kept back, so no sales order follows)."""
    order, _ = MarketplaceOrder.receive(
        channel=EBAY,
        external_id=f"12-{uuid4().int % 10**5:05d}-{uuid4().int % 10**5:05d}",
        buyer_name=buyer_name,
        email=f"{buyer_name}@members.ebay.de",
        recipient="Erika Mustermann",
        street="Heidestraße 17",
        postal_code="51147",
        city="Köln",
        country_code="DE",
        shipping_cents=590,
        paid_at=clock.now(),
        lines=[
            ReceivedLine(
                line_ref="1", sku="X", variant_id=None, title="?", quantity=1, unit_price_cents=100
            )
        ],
        problem="",
        now=clock.now(),
    )
    async with marketplace.uow_factory() as uow:
        uow.orders.add(order)
        await uow.commit()


def notification(username: str, topic: str = ACCOUNT_DELETION_TOPIC) -> bytes:
    return json.dumps(
        {
            "metadata": {"topic": topic, "schemaVersion": "1.0", "deprecated": False},
            "notification": {
                "notificationId": str(uuid4()),
                "eventDate": "2026-10-29T12:00:00.000Z",
                "publishDate": "2026-10-29T12:00:00.100Z",
                "publishAttemptCount": 1,
                "data": {"username": username, "userId": "a1B2c3D4e5F", "eiasToken": ""},
            },
        },
        separators=(",", ":"),
    ).encode()


class TestAccountDeletion:
    async def test_a_closed_account_takes_the_buyers_data_with_it(
        self, marketplace: Marketplace, deletions: AccountDeletionService, clock: FixedClock
    ) -> None:
        await received(marketplace, TEST_BUYER_NAME, clock)
        # eBay's user names do not depend on case.
        await received(marketplace, TEST_BUYER_NAME.upper(), clock)
        await received(marketplace, "max_sammler", clock)

        receipt = await deletions.close_test_account()

        assert receipt == DeletionReceipt(DeletionOutcome.ERASED, erased_orders=2)
        orders = [view.order for view in await marketplace.orders.recent()]
        erased = [order for order in orders if order.buyer_erased_at is not None]
        assert len(erased) == 2
        for order in erased:
            assert (order.buyer_name, order.email, order.recipient) == ("", "", "")
            assert (order.street, order.postal_code, order.city) == ("", "", "")
            # What the order was stays: the shop's books need it.
            assert order.total_cents == 690
        (kept,) = [order for order in orders if order.buyer_erased_at is None]
        assert kept.buyer_name == "max_sammler"
        assert kept.recipient == "Erika Mustermann"

    async def test_a_second_notification_finds_nothing_left(
        self, marketplace: Marketplace, deletions: AccountDeletionService, clock: FixedClock
    ) -> None:
        await received(marketplace, TEST_BUYER_NAME, clock)
        await deletions.close_test_account()

        assert (await deletions.close_test_account()).outcome is DeletionOutcome.UNKNOWN_BUYER

    async def test_a_stranger_is_acknowledged_without_a_trace(
        self, deletions: AccountDeletionService
    ) -> None:
        body = notification("fremder_nutzer")

        receipt = await deletions.receive(body, sign_test_notification(body))

        assert receipt.outcome is DeletionOutcome.UNKNOWN_BUYER

    async def test_without_ebays_signature_nothing_is_deleted(
        self, marketplace: Marketplace, deletions: AccountDeletionService, clock: FixedClock
    ) -> None:
        await received(marketplace, TEST_BUYER_NAME, clock)
        body = notification(TEST_BUYER_NAME)

        with pytest.raises(NotificationSignatureError):
            await deletions.receive(body, "")
        with pytest.raises(NotificationSignatureError):
            await deletions.receive(body, sign_test_notification(notification("jemand")))

        (view,) = await marketplace.orders.recent()
        assert view.order.buyer_erased_at is None

    async def test_other_topics_are_acknowledged(self, deletions: AccountDeletionService) -> None:
        body = notification("x", topic="PRIORITY_LISTING_REVISION")

        receipt = await deletions.receive(body, sign_test_notification(body))

        assert receipt.outcome is DeletionOutcome.OTHER_TOPIC

    @pytest.mark.parametrize(
        "body",
        [b"kein json", b"[]", b'{"metadata":{}}', notification("")],
    )
    async def test_a_body_that_is_no_notification(
        self, deletions: AccountDeletionService, body: bytes
    ) -> None:
        with pytest.raises(NotificationInvalidError):
            await deletions.receive(body, sign_test_notification(body))


class TestAccountDeletionWhileOff:
    @pytest.fixture
    def deletions(
        self,
        settings: Settings,
        session_factory: async_sessionmaker[AsyncSession],
        clock: FixedClock,
    ) -> AccountDeletionService:
        return build_account_deletions(settings, session_factory, None, clock)

    async def test_with_nothing_held_ebay_hears_all_is_done(
        self, deletions: AccountDeletionService
    ) -> None:
        receipt = await deletions.receive(notification("irgendwer"), "")

        assert receipt.outcome is DeletionOutcome.NOTHING_HELD
        assert not deletions.checks_signatures

    async def test_with_buyer_data_held_ebay_tries_again(
        self, deletions: AccountDeletionService, marketplace: Marketplace, clock: FixedClock
    ) -> None:
        await received(marketplace, "max_sammler", clock)

        with pytest.raises(DeletionsUnverifiableError):
            await deletions.receive(notification("max_sammler"), "")
