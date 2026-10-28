"""The sales model without a database: money, addresses, cart, order life cycle, address book."""

import re
from datetime import UTC, datetime, timedelta
from typing import Final
from uuid import UUID, uuid4

import pytest

from modellbahn.modules.sales.application import mails
from modellbahn.modules.sales.domain.errors import (
    AddressBookFullError,
    CartFullError,
    InvalidFieldError,
    InvalidOrderStateError,
    OrderNotPayableError,
)
from modellbahn.modules.sales.domain.events import (
    OrderCancelled,
    OrderPaid,
    OrderPlaced,
    OrderShipped,
)
from modellbahn.modules.sales.domain.model import (
    ADDRESS_BOOK_MAX_SIZE,
    CART_LIFETIME,
    CART_MAX_LINES,
    DOMESTIC_RATE_CENTS,
    EU_RATE_CENTS,
    PAYMENT_TIMEOUT,
    SHIPPING_ZONES,
    CancelReason,
    Cart,
    ChargeResult,
    CustomerAddress,
    Order,
    OrderStatus,
    PaymentStatus,
    PostalAddress,
    PricedItem,
    ShippingZone,
    Totals,
    after_removal,
    included_vat,
    make_default,
    normalize_email,
    order_number,
    shipping_zone,
)
from modellbahn.modules.site.contracts.next_fair import NextFair
from modellbahn.platform.mail import compose

NOW = datetime(2026, 10, 25, 9, 0, tzinfo=UTC)
EU_MEMBER_STATES: Final = 27


def address(country: str = "DE", postal_code: str = "38707") -> PostalAddress:
    return PostalAddress.create(
        recipient=" Erika   Mustermann ",
        street="Bahnhofstraße 12",
        postal_code=postal_code,
        city="Altenau",
        country_code=country,
    )


def item(price: int = 4990, quantity: int = 1) -> PricedItem:
    return PricedItem(
        variant_id=uuid4(),
        product_slug="stellwerk-altenau",
        sku="MB-000001-H0-B",
        title="Stellwerk Altenau · H0 · bemalt",
        scale_code="H0",
        finish_code="painted",
        unit_price_cents=price,
        quantity=quantity,
        image_asset_id=None,
    )


def placed(*items: PricedItem, country: str = "DE") -> tuple[Order, OrderPlaced]:
    return Order.place(
        number=order_number(2026, 42),
        public_token="token",
        items=list(items) or [item()],
        email="Erika@Example.DE",
        address=address(country, "38707" if country == "DE" else "6020"),
        customer_account_id=None,
        checkout_key=uuid4(),
        checkout_fingerprint="0" * 64,
        now=NOW,
    )


def captured() -> ChargeResult:
    return ChargeResult(captured=True, provider="mock", provider_ref=f"mock_{uuid4().hex}")


def declined() -> ChargeResult:
    return ChargeResult(
        captured=False, provider="mock", provider_ref=f"mock_{uuid4().hex}", failure_code="declined"
    )


class TestMoney:
    @pytest.mark.parametrize(
        ("gross", "vat"),
        [(0, 0), (119, 19), (100, 16), (8480, 1354), (5000, 798), (1, 0), (3, 0), (4, 1)],
    )
    def test_included_vat_rounds_half_up(self, gross: int, vat: int) -> None:
        assert included_vat(gross) == vat

    def test_negative_amounts_are_a_bug(self) -> None:
        with pytest.raises(ValueError, match="never negative"):
            included_vat(-1)

    def test_shipping_is_a_flat_rate_and_never_free(self) -> None:
        germany = shipping_zone("DE")
        assert germany.cost(4999) == DOMESTIC_RATE_CENTS
        assert germany.cost(500_000) == DOMESTIC_RATE_CENTS
        assert shipping_zone("AT").cost(9999) == EU_RATE_CENTS
        assert shipping_zone("FR").cost(100_000) == EU_RATE_CENTS
        assert germany.cost(0) == 0

    def test_a_zone_may_still_ship_free_from_a_threshold(self) -> None:
        zone = ShippingZone("DE", "Deutschland", 490, re.compile(r"^\d{5}$"), free_from_cents=5000)
        assert (zone.cost(4999), zone.cost(5000)) == (490, 0)

    def test_the_whole_eu_is_shipped_to_with_germany_first(self) -> None:
        codes = list(SHIPPING_ZONES)
        assert codes[0] == "DE"
        assert len(codes) == EU_MEMBER_STATES
        assert {"AT", "FR", "NL", "PL", "IE", "CY"} <= set(codes)

    @pytest.mark.parametrize(
        ("country", "typed", "stored"),
        [
            ("NL", "1012 ab", "1012 AB"),
            ("PL", "00-950", "00-950"),
            ("IE", "d02  x285", "D02 X285"),
            ("SE", "114 55", "114 55"),
            ("LU", "L-1450", "L-1450"),
        ],
    )
    def test_eu_postal_codes_are_normalised(self, country: str, typed: str, stored: str) -> None:
        address = PostalAddress.create(
            recipient="Erika Mustermann",
            street="Hauptstraße 1",
            postal_code=typed,
            city="Irgendwo",
            country_code=country,
        )
        assert address.postal_code == stored

    def test_a_postal_code_of_another_country_is_refused(self) -> None:
        with pytest.raises(InvalidFieldError) as error:
            PostalAddress.create(
                recipient="Erika Mustermann",
                street="Hauptstraße 1",
                postal_code="12345",
                city="Wien",
                country_code="AT",
            )
        assert error.value.field == "postal_code"

    def test_totals_add_shipping_and_contain_vat(self) -> None:
        totals = Totals.of(3990, shipping_zone("DE"))
        assert (totals.subtotal_cents, totals.shipping_cents, totals.total_cents) == (
            3990,
            590,
            4580,
        )
        assert totals.tax_cents == included_vat(4580)

    def test_unknown_countries_are_not_shipped_to(self) -> None:
        with pytest.raises(InvalidFieldError) as error:
            shipping_zone("CH")
        assert (error.value.field, error.value.code) == ("country_code", "not_shipped")

    def test_order_numbers(self) -> None:
        assert order_number(2026, 42) == "MB-2026-00042"
        assert order_number(2027, 123456) == "MB-2027-123456"


class TestAddresses:
    def test_texts_are_tidied(self) -> None:
        tidy = address()
        assert tidy.recipient == "Erika Mustermann"
        assert tidy.lines() == [
            "Erika Mustermann",
            "Bahnhofstraße 12",
            "38707 Altenau",
            "Deutschland",
        ]

    def test_country_codes_are_upper_case(self) -> None:
        assert address("at", "6020").country_code == "AT"

    @pytest.mark.parametrize(
        ("country", "code"), [("DE", "3870"), ("DE", "ABCDE"), ("AT", "60201")]
    )
    def test_postal_codes_follow_the_country(self, country: str, code: str) -> None:
        with pytest.raises(InvalidFieldError) as error:
            address(country, code)
        assert error.value.field == "postal_code"

    @pytest.mark.parametrize("field", ["recipient", "street", "city"])
    def test_required_texts(self, field: str) -> None:
        values = {
            "recipient": "Erika",
            "street": "Weg 1",
            "postal_code": "38707",
            "city": "Altenau",
            "country_code": "DE",
            field: "   ",
        }
        with pytest.raises(InvalidFieldError) as error:
            PostalAddress.create(**values)
        assert (error.value.field, error.value.code) == (field, "required")

    def test_overlong_texts(self) -> None:
        with pytest.raises(InvalidFieldError) as error:
            PostalAddress.create(
                recipient="x" * 81,
                street="Weg 1",
                postal_code="38707",
                city="Altenau",
                country_code="DE",
            )
        assert error.value.code == "too_long"

    @pytest.mark.parametrize(
        ("raw", "normal"),
        [
            (" Erika@Example.DE ", "Erika@example.de"),
            ("a.b+c@sub.example.org", "a.b+c@sub.example.org"),
        ],
    )
    def test_email_addresses(self, raw: str, normal: str) -> None:
        assert normalize_email(raw) == normal

    @pytest.mark.parametrize(
        "raw", ["", "erika", "erika@", "@example.de", "erika@example", "a b@c.de"]
    )
    def test_invalid_email_addresses(self, raw: str) -> None:
        with pytest.raises(InvalidFieldError):
            normalize_email(raw)


class TestCart:
    def test_quantities_add_change_and_remove(self) -> None:
        cart = Cart.start(NOW)
        variant = uuid4()
        later = NOW + timedelta(days=3)
        cart.set_quantity(variant, 2, NOW)
        cart.set_quantity(variant, 5, later)
        line = cart.line_for(variant)
        assert line is not None
        assert line.quantity == 5
        assert cart.expires_at == later + CART_LIFETIME
        cart.set_quantity(variant, 0, later)
        assert cart.lines == []

    def test_removing_what_is_not_there_is_fine(self) -> None:
        cart = Cart.start(NOW)
        cart.set_quantity(uuid4(), 0, NOW)
        assert cart.lines == []

    @pytest.mark.parametrize("quantity", [-1, 100])
    def test_quantities_are_limited(self, quantity: int) -> None:
        with pytest.raises(InvalidFieldError) as error:
            Cart.start(NOW).set_quantity(uuid4(), quantity, NOW)
        assert error.value.field == "quantity"

    def test_the_number_of_lines_is_limited(self) -> None:
        cart = Cart.start(NOW)
        for _ in range(CART_MAX_LINES):
            cart.set_quantity(uuid4(), 1, NOW)
        with pytest.raises(CartFullError):
            cart.set_quantity(uuid4(), 1, NOW)

    def test_expiry(self) -> None:
        cart = Cart.start(NOW)
        assert not cart.is_expired(NOW + CART_LIFETIME - timedelta(seconds=1))
        assert cart.is_expired(NOW + CART_LIFETIME)

    def test_clear(self) -> None:
        cart = Cart.start(NOW)
        cart.set_quantity(uuid4(), 1, NOW)
        cart.clear(NOW)
        assert cart.lines == []


class TestOrder:
    def test_placing_freezes_lines_and_totals(self) -> None:
        order, event = placed(item(4990, 2), item(1290))
        assert order.status is OrderStatus.PENDING_PAYMENT
        assert [line.line_total_cents for line in order.lines] == [9980, 1290]
        assert [line.position for line in order.lines] == [0, 1]
        assert (order.subtotal_cents, order.shipping_cents, order.total_cents) == (
            11270,
            590,
            11860,
        )
        assert order.tax_cents == included_vat(11860)
        assert order.email == "Erika@example.de"
        assert order.item_count == 3
        assert order.is_guest_order
        assert isinstance(event, OrderPlaced)
        assert event.public_payload() == {
            "order_id": str(order.id),
            "number": "MB-2026-00042",
            "total_cents": 11860,
        }

    def test_shipping_depends_on_the_country(self) -> None:
        order, _ = placed(item(4990), country="AT")
        assert order.shipping_cents == EU_RATE_CENTS

    def test_an_order_needs_lines(self) -> None:
        with pytest.raises(ValueError, match="at least one line"):
            Order.place(
                number="MB-2026-00001",
                public_token="t",
                items=[],
                email="a@b.de",
                address=address(),
                customer_account_id=None,
                checkout_key=uuid4(),
                checkout_fingerprint="0" * 64,
                now=NOW,
            )

    def test_a_declined_payment_keeps_the_order_open(self) -> None:
        order, _ = placed()
        key = uuid4()
        events = order.record_payment(
            declined(), idempotency_key=key, request_fingerprint="f", now=NOW
        )
        assert events == []
        assert order.status is OrderStatus.PENDING_PAYMENT
        payment = order.payment_with_key(key)
        assert payment is not None
        assert (payment.status, payment.failure_code) == (PaymentStatus.FAILED, "declined")
        assert order.payment_due_at == NOW + PAYMENT_TIMEOUT

    def test_a_captured_payment_makes_it_binding(self) -> None:
        order, _ = placed()
        order.record_payment(declined(), idempotency_key=uuid4(), request_fingerprint="f", now=NOW)
        later = NOW + timedelta(minutes=2)
        (event,) = order.record_payment(
            captured(), idempotency_key=uuid4(), request_fingerprint="f", now=later
        )
        assert isinstance(event, OrderPaid)
        assert (order.status, order.paid_at) == (OrderStatus.PAID, later)
        assert order.captured_payment is order.payments[1]
        assert order.payment_due_at is None
        with pytest.raises(OrderNotPayableError):
            order.record_payment(
                captured(), idempotency_key=uuid4(), request_fingerprint="f", now=later
            )

    def test_shipping(self) -> None:
        order, _ = placed()
        with pytest.raises(InvalidOrderStateError):
            order.ship(carrier="", tracking_number="", now=NOW)
        order.record_payment(captured(), idempotency_key=uuid4(), request_fingerprint="f", now=NOW)
        event = order.ship(carrier=" DHL ", tracking_number=" 00340434 ", now=NOW)
        assert isinstance(event, OrderShipped)
        assert (order.status, order.carrier, order.tracking_number) == (
            OrderStatus.SHIPPED,
            "DHL",
            "00340434",
        )
        with pytest.raises(InvalidOrderStateError):
            order.cancel(reason=CancelReason.BY_SHOP, note="", now=NOW)

    def test_cancelling_an_open_order(self) -> None:
        order, _ = placed()
        event = order.cancel(reason=CancelReason.PAYMENT_TIMEOUT, note="", now=NOW)
        assert isinstance(event, OrderCancelled)
        assert not event.refunded
        assert (order.status, order.cancel_reason) == (
            OrderStatus.CANCELLED,
            CancelReason.PAYMENT_TIMEOUT,
        )
        with pytest.raises(OrderNotPayableError):
            order.record_payment(
                captured(), idempotency_key=uuid4(), request_fingerprint="f", now=NOW
            )

    def test_cancelling_a_paid_order_refunds_it(self) -> None:
        order, _ = placed()
        order.record_payment(captured(), idempotency_key=uuid4(), request_fingerprint="f", now=NOW)
        event = order.cancel(reason=CancelReason.BY_SHOP, note="  Doppelt bestellt ", now=NOW)
        assert event.refunded
        assert order.payments[0].status is PaymentStatus.REFUNDED
        assert order.cancel_note == "Doppelt bestellt"
        with pytest.raises(InvalidOrderStateError):
            order.payments[0].refund(NOW)

    def test_overdue(self) -> None:
        order, _ = placed()
        assert not order.is_overdue(NOW + PAYMENT_TIMEOUT - timedelta(seconds=1))
        assert order.is_overdue(NOW + PAYMENT_TIMEOUT)

    def test_adoption_only_for_guest_orders(self) -> None:
        order, _ = placed()
        account = uuid4()
        assert order.adopt(account, NOW)
        assert order.customer_account_id == account
        assert not order.adopt(uuid4(), NOW)
        assert order.customer_account_id == account


class TestAddressBook:
    def entry(self, account: UUID, book: list[CustomerAddress], at: datetime) -> CustomerAddress:
        created = CustomerAddress.create(
            account_id=account, label=" Zuhause ", address=address(), existing=book, now=at
        )
        book.append(created)
        return created

    def test_the_first_entry_is_the_default(self) -> None:
        account = uuid4()
        book: list[CustomerAddress] = []
        first = self.entry(account, book, NOW)
        second = self.entry(account, book, NOW + timedelta(minutes=1))
        assert (first.is_default, second.is_default) == (True, False)
        assert first.label == "Zuhause"

    def test_switching_the_default(self) -> None:
        account = uuid4()
        book: list[CustomerAddress] = []
        first = self.entry(account, book, NOW)
        second = self.entry(account, book, NOW)
        make_default(book, second.id, NOW)
        assert (first.is_default, second.is_default) == (False, True)

    def test_after_removing_the_default_the_oldest_takes_over(self) -> None:
        account = uuid4()
        book: list[CustomerAddress] = []
        first = self.entry(account, book, NOW)
        second = self.entry(account, book, NOW + timedelta(minutes=1))
        third = self.entry(account, book, NOW + timedelta(minutes=2))
        make_default(book, third.id, NOW)
        book.remove(third)
        after_removal(book, NOW)
        assert (first.is_default, second.is_default) == (True, False)

    def test_the_book_is_limited(self) -> None:
        account = uuid4()
        book: list[CustomerAddress] = []
        for _ in range(ADDRESS_BOOK_MAX_SIZE):
            self.entry(account, book, NOW)
        with pytest.raises(AddressBookFullError):
            self.entry(account, book, NOW)

    def test_changing_an_entry(self) -> None:
        account = uuid4()
        book: list[CustomerAddress] = []
        entry = self.entry(account, book, NOW)
        later = NOW + timedelta(days=1)
        entry.change(label="Büro", address=address("AT", "6020"), now=later)
        assert (entry.label, entry.address.country_code, entry.updated_at) == ("Büro", "AT", later)


class TestMails:
    def test_receipt_and_dispatch_name_the_next_fair(self) -> None:
        order, _ = placed()
        fair = NextFair(
            name="Kleinserienmesse Dresden",
            city="Dresden",
            venue="JohannStadthalle",
            booth="",
            starts_on=datetime(2026, 11, 7, tzinfo=UTC).date(),
            ends_on=datetime(2026, 11, 7, tzinfo=UTC).date(),
        )
        receipt = mails.received_mail(
            order, base_url="https://shop.test", shop_name="adp-Modelle", next_fair=fair
        )
        hint = receipt.closing[-1]
        assert "„Kleinserienmesse Dresden“" in hint
        assert "7. November 2026, JohannStadthalle, Dresden" in hint
        assert hint.endswith("Alle Termine: https://shop.test/termine")
        shipped = mails.shipped_mail(order, base_url="https://shop.test", next_fair=fair)
        assert shipped.closing[-1] == hint

    def test_without_a_fair_the_mails_stay_as_they_were(self) -> None:
        order, _ = placed()
        shipped = mails.shipped_mail(order, base_url="https://shop.test")
        assert shipped.closing == ("Viel Freude beim Bauen!",)


class TestSenderFooter:
    def test_every_mail_ends_with_who_sent_it(self) -> None:
        order, _ = placed()
        content = mails.shipped_mail(order, base_url="https://shop.test")
        sender = (
            "adp-Modelle · Johann-Leon Diesterhaupt",
            "Glambecker Straße 2, 17235 Neustrelitz",
        )
        rendered = compose(content, to=order.email, shop_name="adp-Modelle", sender=sender)
        assert "-- \nadp-Modelle · Johann-Leon Diesterhaupt\nGlambecker Straße 2" in rendered.text
        assert "Glambecker Straße 2, 17235 Neustrelitz" in rendered.html
