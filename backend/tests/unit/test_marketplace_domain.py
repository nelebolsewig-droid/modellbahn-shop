"""The marketplace model: the eBay account, listings and orders, without a database."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from modellbahn.modules.marketplace.domain.errors import (
    ConnectionStateInvalidError,
    InvalidFieldError,
)
from modellbahn.modules.marketplace.domain.events import (
    MarketplaceOrderCancelled,
    MarketplaceOrderReceived,
)
from modellbahn.modules.marketplace.domain.model import (
    CONNECT_STATE_LIFETIME,
    EBAY,
    Blocker,
    ConnectionStatus,
    EbayAccount,
    Listing,
    ListingItem,
    ListingStatus,
    MarketplaceOrder,
    MarketplaceOrderStatus,
    ReceivedLine,
    Tokens,
)

NOW = datetime(2026, 10, 22, 10, 0, tzinfo=UTC)


def connected(seller: str = "adp-modelle") -> EbayAccount:
    account = EbayAccount.new(NOW)
    account.connect(
        seller_name=seller,
        tokens=Tokens(
            access_token="sealed-access",
            access_expires_at=NOW + timedelta(hours=2),
            refresh_token="sealed-refresh",
            refresh_expires_at=NOW + timedelta(days=548),
        ),
        now=NOW,
    )
    return account


def ready() -> EbayAccount:
    account = connected()
    account.change_settings(
        fulfillment_policy_id="111", payment_policy_id="222", return_policy_id="333", now=NOW
    )
    account.location_created(NOW)
    return account


def received(*, variant_known: bool = True, problem: str = "") -> MarketplaceOrder:
    order, _ = MarketplaceOrder.receive(
        channel=EBAY,
        external_id="12-34567-89012",
        buyer_name="erika_kauft",
        email="erika@example.de",
        recipient="Erika Mustermann",
        street="Bahnhofstraße 12",
        postal_code="38707",
        city="Altenau",
        country_code="de",
        shipping_cents=590,
        paid_at=NOW,
        lines=[
            ReceivedLine(
                line_ref="10001",
                sku="MB-000001-H0-F",
                variant_id=uuid4() if variant_known else None,
                title="IFA W50 Kipper",
                quantity=2,
                unit_price_cents=4990,
            )
        ],
        problem=problem,
        now=NOW,
    )
    return order


class TestAccount:
    def test_a_new_account_lists_everything_that_is_missing(self) -> None:
        assert EbayAccount.new(NOW).blockers == list(Blocker)

    def test_connected_with_policies_and_location_it_is_ready(self) -> None:
        account = ready()
        assert account.status is ConnectionStatus.CONNECTED
        assert account.blockers == []

    def test_the_consent_answer_must_come_from_here_and_in_time(self) -> None:
        account = EbayAccount.new(NOW)
        account.begin_connect("a" * 64, NOW)
        account.check_state("a" * 64, NOW + CONNECT_STATE_LIFETIME)
        # Used once: the same answer again is refused.
        with pytest.raises(ConnectionStateInvalidError):
            account.check_state("a" * 64, NOW)

    @pytest.mark.parametrize(
        ("state", "later"),
        [("b" * 64, timedelta(0)), ("a" * 64, CONNECT_STATE_LIFETIME + timedelta(seconds=1))],
    )
    def test_a_foreign_or_late_answer_is_refused(self, state: str, later: timedelta) -> None:
        account = EbayAccount.new(NOW)
        account.begin_connect("a" * 64, NOW)
        with pytest.raises(ConnectionStateInvalidError):
            account.check_state(state, NOW + later)

    def test_another_ebay_account_forgets_the_settings_of_the_first(self) -> None:
        account = ready()
        account.connect(
            seller_name="jemand-anders",
            tokens=Tokens("x", NOW, "y", NOW + timedelta(days=1)),
            now=NOW,
        )
        assert account.fulfillment_policy_id == ""
        assert not account.location_ready

    def test_expired_consent_keeps_the_settings(self) -> None:
        account = ready()
        account.expire(NOW)
        assert account.status is ConnectionStatus.EXPIRED
        assert account.refresh_token == ""
        assert account.blockers == [Blocker.NOT_CONNECTED]

    def test_disconnecting_forgets_everything_of_the_account(self) -> None:
        account = ready()
        account.disconnect(NOW)
        assert account.seller_name == ""
        assert account.blockers == list(Blocker)

    @pytest.mark.parametrize(
        ("change", "field"),
        [
            ({"price_markup_percent": 101}, "price_markup_percent"),
            ({"price_markup_percent": -1}, "price_markup_percent"),
            ({"made_to_order_quantity": 0}, "made_to_order_quantity"),
            ({"made_to_order_quantity": 21}, "made_to_order_quantity"),
            ({"payment_policy_id": "nicht gültig"}, "payment_policy_id"),
        ],
    )
    def test_settings_have_limits(self, change: dict[str, object], field: str) -> None:
        with pytest.raises(InvalidFieldError) as caught:
            ready().change_settings(**change, now=NOW)  # type: ignore[arg-type]
        assert caught.value.field == field

    @pytest.mark.parametrize(
        ("markup", "price", "expected"),
        [(0, 4990, 4990), (10, 4990, 5489), (15, 1999, 2299), (100, 1, 2)],
    )
    def test_the_markup_rounds_half_up(self, markup: int, price: int, expected: int) -> None:
        account = ready()
        account.change_settings(price_markup_percent=markup, now=NOW)
        assert account.listing_price(price) == expected

    def test_made_to_order_offers_at_least_the_cap(self) -> None:
        account = ready()
        account.change_settings(made_to_order_quantity=3, now=NOW)
        assert account.listing_quantity(free_units=0, made_to_order=True) == 3
        assert account.listing_quantity(free_units=5, made_to_order=True) == 5
        assert account.listing_quantity(free_units=0, made_to_order=False) == 0
        assert account.listing_quantity(free_units=2, made_to_order=False) == 2


class TestListing:
    def listing(self) -> Listing:
        return Listing.create(
            product_id=uuid4(), scale_code="H0", group_key="MB-000001-H0", now=NOW
        )

    def item(self, listing: Listing, sku: str, offer_id: str = "") -> ListingItem:
        return ListingItem(
            listing_id=listing.id,
            sku=sku,
            variant_id=uuid4(),
            offer_id=offer_id,
            quantity=1,
            price_cents=4990,
        )

    def test_a_new_listing_is_wanted_and_due(self) -> None:
        listing = self.listing()
        assert listing.wanted
        assert listing.needs_sync
        assert listing.status is ListingStatus.PENDING
        assert not listing.is_up

    def test_synced_it_is_up_with_its_offers(self) -> None:
        listing = self.listing()
        event = listing.synced(
            external_id="110012345678",
            items=[self.item(listing, "MB-000001-H0-B", "O1"), self.item(listing, "X")],
            now=NOW,
        )
        assert listing.is_up
        assert not listing.needs_sync
        assert listing.offer_ids == {"MB-000001-H0-B": "O1"}
        assert event.status == "active"

    def test_a_refusal_keeps_the_old_version_up(self) -> None:
        listing = self.listing()
        listing.synced(external_id="110012345678", items=[], now=NOW)
        listing.failed(code="25002", message="Fehler " * 200, now=NOW)
        assert listing.is_up
        assert listing.status is ListingStatus.FAILED
        assert len(listing.error_message) <= 500

    def test_held_back_it_is_off_ebay_with_the_reason(self) -> None:
        listing = self.listing()
        listing.synced(external_id="110012345678", items=[], now=NOW)
        listing.held_back(code="no_photo", message="Kein Foto.", now=NOW)
        assert not listing.is_up
        assert listing.error_code == "no_photo"

    def test_wanting_an_ended_listing_again_brings_it_back(self) -> None:
        listing = self.listing()
        listing.want(False, NOW)
        listing.ended(NOW)
        listing.want(True, NOW + timedelta(minutes=1))
        assert listing.status is ListingStatus.PENDING
        assert listing.needs_sync


class TestOrder:
    def test_a_clean_order_is_handed_to_the_sales(self) -> None:
        order, events = MarketplaceOrder.receive(
            channel=EBAY,
            external_id="12-34567-89012",
            buyer_name="b",
            email="b@example.de",
            recipient="B",
            street="S 1",
            postal_code="10115",
            city="Berlin",
            country_code="DE",
            shipping_cents=590,
            paid_at=NOW,
            lines=[ReceivedLine("1", "SKU", uuid4(), "T", 2, 1000)],
            problem="",
            now=NOW,
        )
        assert order.status is MarketplaceOrderStatus.RECEIVED
        assert order.total_cents == 2590
        assert [type(event) for event in events] == [MarketplaceOrderReceived]

    def test_an_unknown_article_is_rejected(self) -> None:
        order = received(variant_known=False)
        assert order.status is MarketplaceOrderStatus.REJECTED
        assert order.problem == "unknown article"

    def test_an_address_problem_is_rejected(self) -> None:
        order = received(problem="address postal_code: invalid")
        assert order.status is MarketplaceOrderStatus.REJECTED
        assert order.country_code == "DE"

    def test_a_cancellation_reaches_the_sales_only_for_handed_over_orders(self) -> None:
        order = received()
        assert [type(e) for e in order.cancel(NOW)] == [MarketplaceOrderCancelled]
        assert order.status is MarketplaceOrderStatus.CANCELLED
        assert order.cancel(NOW) == []
        assert received(variant_known=False).cancel(NOW) == []

    def test_a_shipped_order_stays_shipped(self) -> None:
        order = received()
        order.shipment_failed("eBay sagt nein", NOW)
        assert order.problem == "eBay sagt nein"
        order.shipment_reported(NOW)
        assert order.problem == ""
        assert order.cancel(NOW) == []
        assert order.status is MarketplaceOrderStatus.SHIPPED
