"""Sales use cases against the database: cart, checkout, payment, history, address book."""

import asyncio
from datetime import timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine

from modellbahn.modules.catalog.application.services import CatalogService, ProductDetails
from modellbahn.modules.identity.application.services import IdentityService
from modellbahn.modules.inventory.application.allocation import AllocationService
from modellbahn.modules.inventory.application.locations import LocationService
from modellbahn.modules.inventory.application.scanning import ScanService
from modellbahn.modules.inventory.application.units import UnitService
from modellbahn.modules.media.application.services import MediaService
from modellbahn.modules.sales.application.addresses import AddressService
from modellbahn.modules.sales.application.cart import CartService
from modellbahn.modules.sales.application.checkout import (
    AddressInput,
    Buyer,
    CheckoutRequest,
    CheckoutService,
)
from modellbahn.modules.sales.application.orders import OrderService
from modellbahn.modules.sales.domain.errors import (
    AddressNotFoundError,
    CartItemsUnavailableError,
    EmptyCartError,
    IdempotencyKeyReusedError,
    InvalidFieldError,
    InvalidOrderStateError,
    OrderNotFoundError,
    OrderNotPayableError,
    OrderNotPickedError,
    PaymentUnavailableError,
    PriceChangedError,
    VariantUnavailableError,
)
from modellbahn.modules.sales.domain.model import (
    CART_LIFETIME,
    PAYMENT_TIMEOUT,
    CancelReason,
    OrderStatus,
    PaymentStatus,
)
from modellbahn.modules.sales.infrastructure.tables import orders as orders_table
from modellbahn.platform.clock import FixedClock
from modellbahn.platform.mail import InMemoryMailer
from modellbahn.platform.outbox import outbox_table
from tests.conftest import PUBLIC_BASE_URL, Deliver
from tests.inventory_support import pick_everything, staff_member, stock_up
from tests.media_support import InMemoryMediaStorage
from tests.sales_support import ADDRESS, filled_cart, place, shop_product, variant_id
from tests.support import mails_to, token_from

PASSWORD = "Gleisplan-Stellwerk-42"


@pytest.fixture
async def product(
    catalog: CatalogService,
    media: MediaService,
    media_storage: InMemoryMediaStorage,
    deliver: Deliver,
) -> ProductDetails:
    return await shop_product(catalog, media, media_storage, deliver)


@pytest.fixture
def painted(product: ProductDetails) -> UUID:
    return variant_id(product, "H0", "painted")


@pytest.fixture
def unpainted(product: ProductDetails) -> UUID:
    return variant_id(product, "H0", "unpainted")


async def event_types(engine: AsyncEngine, prefix: str = "sales.") -> list[str]:
    async with engine.connect() as connection:
        rows = await connection.execute(
            select(outbox_table.c.event_type)
            .where(outbox_table.c.event_type.startswith(prefix))
            .order_by(outbox_table.c.occurred_at, outbox_table.c.id)
        )
        return list(rows.scalars())


async def order_count(engine: AsyncEngine) -> int:
    async with engine.connect() as connection:
        return int(await connection.scalar(select(func.count()).select_from(orders_table)) or 0)


async def verified_customer(
    identity: IdentityService, deliver: Deliver, mailer: InMemoryMailer, email: str
) -> UUID:
    await identity.register_customer(email=email, password=PASSWORD, display_name="Erika")
    await deliver()
    started = await identity.verify_email(
        token=token_from(mails_to(mailer, email)[-1]), password=PASSWORD, user_agent=None
    )
    return started.account.id


class TestCart:
    async def test_no_cart_is_an_empty_cart(self, carts: CartService) -> None:
        view = await carts.view(None)
        assert (view.cart_id, view.items, view.item_count) == (None, [], 0)
        assert view.totals.total_cents == 0
        assert not view.ready_for_checkout
        assert (await carts.view(uuid4())).items == []

    async def test_lines_are_priced_from_the_catalogue(
        self, carts: CartService, catalog: CatalogService, painted: UUID, unpainted: UUID
    ) -> None:
        cart = await filled_cart(carts, (painted, 2), (unpainted, 1))
        view = await carts.view(cart)
        assert [(i.variant.sku[-1], i.quantity, i.line_total_cents) for i in view.items] == [
            ("B", 2, 9980),
            ("U", 1, 2990),
        ]
        assert view.items[0].variant.title == "Stellwerk Altenau · H0 · bemalt"
        assert view.items[0].image is not None
        assert (view.totals.subtotal_cents, view.totals.shipping_cents) == (12970, 590)
        assert view.item_count == 3
        assert view.ready_for_checkout

        await catalog.change_variant(painted, expected_version=None, price_cents=5490)
        assert (await carts.view(cart)).totals.subtotal_cents == 13970

    async def test_small_orders_pay_shipping(self, carts: CartService, unpainted: UUID) -> None:
        view = await carts.view(await filled_cart(carts, (unpainted, 1)))
        assert (view.totals.shipping_cents, view.totals.total_cents) == (590, 3580)

    async def test_quantities_change_and_lines_leave(
        self, carts: CartService, painted: UUID
    ) -> None:
        cart = await filled_cart(carts, (painted, 1))
        assert (await carts.set_quantity(cart, painted, 4)).items[0].quantity == 4
        assert (await carts.set_quantity(cart, painted, 0)).items == []

    async def test_only_variants_on_sale_go_in(
        self, carts: CartService, catalog: CatalogService, product: ProductDetails, painted: UUID
    ) -> None:
        with pytest.raises(VariantUnavailableError):
            await carts.set_quantity(None, uuid4(), 1)
        cart = await filled_cart(carts, (painted, 1))
        await catalog.archive(product.product.id, expected_version=None)
        view = await carts.view(cart)
        assert [item.available for item in view.items] == [False]
        assert (view.item_count, view.totals.total_cents, view.ready_for_checkout) == (0, 0, False)
        with pytest.raises(VariantUnavailableError):
            await carts.set_quantity(cart, painted, 2)
        assert (await carts.set_quantity(cart, painted, 0)).items == []

    async def test_expired_carts_are_empty_and_purged(
        self, carts: CartService, clock: FixedClock, painted: UUID
    ) -> None:
        cart = await filled_cart(carts, (painted, 1))
        clock.advance(CART_LIFETIME)
        assert (await carts.view(cart)).items == []
        fresh = await carts.set_quantity(cart, painted, 1)
        assert fresh.cart_id not in {None, cart}
        assert await carts.purge_expired() == 1


class TestCheckout:
    async def test_a_guest_orders(
        self,
        carts: CartService,
        checkout: CheckoutService,
        engine: AsyncEngine,
        painted: UUID,
        unpainted: UUID,
    ) -> None:
        cart = await filled_cart(carts, (painted, 1), (unpainted, 2))
        result = await place(checkout, carts, cart, email=" Erika@Example.DE ")
        order = result.details.order
        assert not result.replayed
        assert order.number.startswith("MB-2026-")
        assert order.status is OrderStatus.PENDING_PAYMENT
        assert order.is_guest_order
        assert order.email == "Erika@example.de"
        assert [(line.sku[-1], line.quantity, line.unit_price_cents) for line in order.lines] == [
            ("B", 1, 4990),
            ("U", 2, 2990),
        ]
        assert (order.subtotal_cents, order.shipping_cents, order.total_cents) == (
            10970,
            590,
            11560,
        )
        assert order.shipping_address.city == "Altenau"
        assert set(result.details.images) == {order.lines[0].image_asset_id}
        assert len(order.public_token) >= 40
        assert (await carts.view(cart)).items == []
        assert await event_types(engine) == ["sales.order.placed"]

    async def test_shipping_follows_the_address(
        self, carts: CartService, checkout: CheckoutService, unpainted: UUID
    ) -> None:
        cart = await filled_cart(carts, (unpainted, 1))
        request = CheckoutRequest(
            expected_total_cents=2990 + 1690,
            email="erika@example.at",
            address=AddressInput(
                recipient="Erika",
                street="Bahnhofplatz 1",
                postal_code="6020",
                city="Innsbruck",
                country_code="AT",
            ),
        )
        result = await checkout.place_order(
            cart_id=cart, request=request, buyer=None, idempotency_key=uuid4()
        )
        assert result.details.order.shipping_cents == 1690

    async def test_the_same_key_never_orders_twice(
        self, carts: CartService, checkout: CheckoutService, engine: AsyncEngine, painted: UUID
    ) -> None:
        cart = await filled_cart(carts, (painted, 1))
        key = uuid4()
        request = CheckoutRequest(
            expected_total_cents=5580, email="erika@example.de", address=ADDRESS
        )
        first = await checkout.place_order(
            cart_id=cart, request=request, buyer=None, idempotency_key=key
        )
        again = await checkout.place_order(
            cart_id=cart, request=request, buyer=None, idempotency_key=key
        )
        assert again.replayed
        assert again.details.order.id == first.details.order.id
        assert await order_count(engine) == 1
        other = CheckoutRequest(
            expected_total_cents=5580, email="mallory@example.de", address=ADDRESS
        )
        with pytest.raises(IdempotencyKeyReusedError):
            await checkout.place_order(cart_id=cart, request=other, buyer=None, idempotency_key=key)

    async def test_parallel_requests_with_one_key_make_one_order(
        self, carts: CartService, checkout: CheckoutService, engine: AsyncEngine, painted: UUID
    ) -> None:
        cart = await filled_cart(carts, (painted, 1))
        key = uuid4()
        request = CheckoutRequest(
            expected_total_cents=5580, email="erika@example.de", address=ADDRESS
        )
        results = await asyncio.gather(
            *(
                checkout.place_order(cart_id=cart, request=request, buyer=None, idempotency_key=key)
                for _ in range(3)
            )
        )
        assert len({r.details.order.id for r in results}) == 1
        assert await order_count(engine) == 1

    async def test_a_changed_price_orders_nothing(
        self,
        carts: CartService,
        checkout: CheckoutService,
        catalog: CatalogService,
        engine: AsyncEngine,
        painted: UUID,
    ) -> None:
        cart = await filled_cart(carts, (painted, 1))
        await catalog.change_variant(painted, expected_version=None, price_cents=5990)
        request = CheckoutRequest(
            expected_total_cents=5580, email="erika@example.de", address=ADDRESS
        )
        with pytest.raises(PriceChangedError) as error:
            await checkout.place_order(
                cart_id=cart, request=request, buyer=None, idempotency_key=uuid4()
            )
        assert (error.value.expected_cents, error.value.actual_cents) == (5580, 6580)
        assert await order_count(engine) == 0
        assert len((await carts.view(cart)).items) == 1

    async def test_unavailable_lines_block_the_checkout(
        self,
        carts: CartService,
        checkout: CheckoutService,
        catalog: CatalogService,
        painted: UUID,
        unpainted: UUID,
    ) -> None:
        cart = await filled_cart(carts, (painted, 1), (unpainted, 1))
        await catalog.change_variant(unpainted, expected_version=None, active=False)
        with pytest.raises(CartItemsUnavailableError) as error:
            await place(checkout, carts, cart)
        assert error.value.variant_ids == [unpainted]

    async def test_nothing_to_order(self, carts: CartService, checkout: CheckoutService) -> None:
        with pytest.raises(EmptyCartError):
            await place(checkout, carts, uuid4())

    async def test_guests_need_an_email_address_and_an_address(
        self, carts: CartService, checkout: CheckoutService, painted: UUID
    ) -> None:
        cart = await filled_cart(carts, (painted, 1))
        with pytest.raises(InvalidFieldError) as error:
            await place(checkout, carts, cart, email=None)
        assert error.value.field == "email"
        with pytest.raises(InvalidFieldError) as error:
            await place(checkout, carts, cart, address=None)
        assert error.value.field == "address"

    async def test_a_customer_orders_with_the_address_book(
        self,
        carts: CartService,
        checkout: CheckoutService,
        addresses: AddressService,
        orders: OrderService,
        identity: IdentityService,
        deliver: Deliver,
        mailer: InMemoryMailer,
        painted: UUID,
    ) -> None:
        account = await verified_customer(identity, deliver, mailer, "kundin@example.de")
        buyer = Buyer(account_id=account, email="kundin@example.de")
        cart = await filled_cart(carts, (painted, 1))
        first = await place(checkout, carts, cart, buyer=buyer)
        assert first.details.order.customer_account_id == account
        assert first.details.order.email == "kundin@example.de"
        assert await addresses.book(account) == []

        book = await addresses.add(account, label="Werkstatt", address=ADDRESS, default=False)
        cart = await filled_cart(carts, (painted, 1))
        request = CheckoutRequest(expected_total_cents=5580, address_id=book[0].id)
        second = await checkout.place_order(
            cart_id=cart, request=request, buyer=buyer, idempotency_key=uuid4()
        )
        assert second.details.order.shipping_address == book[0].address

        cart = await filled_cart(carts, (painted, 1))
        with pytest.raises(AddressNotFoundError):
            await checkout.place_order(
                cart_id=cart,
                request=CheckoutRequest(expected_total_cents=5580, address_id=uuid4()),
                buyer=buyer,
                idempotency_key=uuid4(),
            )
        saving = CheckoutRequest(
            expected_total_cents=5580,
            address=AddressInput("Kundin", "Weg 2", "10115", "Berlin", "DE"),
            save_address=True,
        )
        await checkout.place_order(
            cart_id=cart, request=saving, buyer=buyer, idempotency_key=uuid4()
        )
        assert [entry.address.city for entry in await addresses.book(account)] == [
            "Altenau",
            "Berlin",
        ]

        history = await orders.customer_orders(account, cursor=None, limit=2)
        assert len(history.items) == 2
        assert history.next_cursor is not None
        rest = await orders.customer_orders(account, cursor=history.next_cursor, limit=2)
        assert [o.number for o in rest.items] == [first.details.order.number]

    async def test_a_guest_order_with_a_verified_address_joins_the_account(
        self,
        carts: CartService,
        checkout: CheckoutService,
        identity: IdentityService,
        deliver: Deliver,
        mailer: InMemoryMailer,
        painted: UUID,
    ) -> None:
        account = await verified_customer(identity, deliver, mailer, "kundin@example.de")
        cart = await filled_cart(carts, (painted, 1))
        result = await place(checkout, carts, cart, email="KUNDIN@example.de")
        assert result.details.order.customer_account_id == account


class TestPayment:
    async def test_declined_then_paid(
        self,
        carts: CartService,
        checkout: CheckoutService,
        engine: AsyncEngine,
        deliver: Deliver,
        mailer: InMemoryMailer,
        painted: UUID,
    ) -> None:
        cart = await filled_cart(carts, (painted, 1))
        order = (await place(checkout, carts, cart)).details.order
        token = order.public_token
        await deliver()
        (received,) = mails_to(mailer, "erika@example.de")
        assert received.subject == f"Bestellung {order.number} eingegangen"
        assert f"{PUBLIC_BASE_URL}/bestellung/{token}/bezahlen" in received.text
        # Placed at 10:00 UTC on 22 October, due 24 hours later, shown in German summer time.
        assert "23.10.2026, 12:00 Uhr" in received.text
        assert "Stellwerk Altenau · H0 · bemalt" in received.text
        assert "49,90\u00a0€" in received.text

        declined = await checkout.pay(
            public_token=token, method="declined", idempotency_key=uuid4()
        )
        assert declined.details.order.status is OrderStatus.PENDING_PAYMENT
        assert [p.status for p in declined.details.order.payments] == [PaymentStatus.FAILED]

        key = uuid4()
        paid = await checkout.pay(public_token=token, method="succeeds", idempotency_key=key)
        assert paid.details.order.status is OrderStatus.PAID
        again = await checkout.pay(public_token=token, method="succeeds", idempotency_key=key)
        assert again.replayed
        assert len(again.details.order.payments) == 2
        with pytest.raises(OrderNotPayableError):
            await checkout.pay(public_token=token, method="succeeds", idempotency_key=uuid4())
        with pytest.raises(IdempotencyKeyReusedError):
            await checkout.pay(public_token=token, method="declined", idempotency_key=key)
        assert await event_types(engine) == ["sales.order.placed", "sales.order.paid"]

        await deliver()
        confirmed = mails_to(mailer, "erika@example.de")[-1]
        assert confirmed.subject == f"Zahlung eingegangen: Bestellung {order.number}"
        assert f"{PUBLIC_BASE_URL}/bestellung/{token}" in confirmed.text

    async def test_a_late_receipt_offers_the_order_instead_of_the_payment(
        self,
        carts: CartService,
        checkout: CheckoutService,
        deliver: Deliver,
        mailer: InMemoryMailer,
        painted: UUID,
    ) -> None:
        cart = await filled_cart(carts, (painted, 1))
        order = (await place(checkout, carts, cart)).details.order
        await checkout.pay(
            public_token=order.public_token, method="succeeds", idempotency_key=uuid4()
        )
        await deliver()
        received, _ = mails_to(mailer, "erika@example.de")
        assert "/bezahlen" not in received.text
        assert "Bitte bezahle bis" not in received.text
        assert "Bestellung ansehen" in received.text

    async def test_a_provider_failure_records_nothing(
        self, carts: CartService, checkout: CheckoutService, orders: OrderService, painted: UUID
    ) -> None:
        cart = await filled_cart(carts, (painted, 1))
        order = (await place(checkout, carts, cart)).details.order
        with pytest.raises(PaymentUnavailableError):
            await checkout.pay(
                public_token=order.public_token, method="fails", idempotency_key=uuid4()
            )
        assert (await orders.by_token(order.public_token)).order.payments == []

    async def test_unknown_orders_and_methods(
        self, carts: CartService, checkout: CheckoutService, painted: UUID
    ) -> None:
        with pytest.raises(OrderNotFoundError):
            await checkout.pay(public_token="nope", method="succeeds", idempotency_key=uuid4())
        cart = await filled_cart(carts, (painted, 1))
        order = (await place(checkout, carts, cart)).details.order
        with pytest.raises(InvalidFieldError):
            await checkout.pay(
                public_token=order.public_token, method="cash", idempotency_key=uuid4()
            )

    async def test_a_key_belongs_to_one_order(
        self, carts: CartService, checkout: CheckoutService, painted: UUID
    ) -> None:
        tokens = []
        for _ in range(2):
            cart = await filled_cart(carts, (painted, 1))
            tokens.append((await place(checkout, carts, cart)).details.order.public_token)
        key = uuid4()
        await checkout.pay(public_token=tokens[0], method="declined", idempotency_key=key)
        with pytest.raises(IdempotencyKeyReusedError):
            await checkout.pay(public_token=tokens[1], method="declined", idempotency_key=key)


class TestAfterTheOrder:
    async def paid_order(
        self, carts: CartService, checkout: CheckoutService, variant: UUID
    ) -> UUID:
        cart = await filled_cart(carts, (variant, 1))
        order = (await place(checkout, carts, cart)).details.order
        await checkout.pay(
            public_token=order.public_token, method="succeeds", idempotency_key=uuid4()
        )
        return order.id

    async def test_shipping_tells_the_customer(
        self,
        carts: CartService,
        checkout: CheckoutService,
        orders: OrderService,
        deliver: Deliver,
        mailer: InMemoryMailer,
        painted: UUID,
        identity: IdentityService,
        locations: LocationService,
        units: UnitService,
        scans: ScanService,
        allocation: AllocationService,
    ) -> None:
        await stock_up(locations, units, painted)
        order_id = await self.paid_order(carts, checkout, painted)
        # Only a completely picked order leaves the workshop.
        with pytest.raises(OrderNotPickedError):
            await orders.ship(order_id, carrier="DHL", tracking_number="00340434")
        await deliver()
        await pick_everything(scans, allocation, order_id, await staff_member(identity))
        shipped = await orders.ship(order_id, carrier="DHL", tracking_number="00340434")
        assert shipped.order.status is OrderStatus.SHIPPED
        with pytest.raises(InvalidOrderStateError):
            await orders.cancel(order_id, note="")
        await deliver()
        subjects = [mail.subject for mail in mails_to(mailer, "erika@example.de")]
        assert subjects[-1].endswith("ist unterwegs")
        assert "00340434" in mails_to(mailer, "erika@example.de")[-1].text

    async def test_cancelling_a_paid_order_refunds_it(
        self,
        carts: CartService,
        checkout: CheckoutService,
        orders: OrderService,
        deliver: Deliver,
        mailer: InMemoryMailer,
        painted: UUID,
    ) -> None:
        order_id = await self.paid_order(carts, checkout, painted)
        cancelled = await orders.cancel(order_id, note="Auf Wunsch der Kundin")
        order = cancelled.order
        assert (order.status, order.cancel_reason) == (OrderStatus.CANCELLED, CancelReason.BY_SHOP)
        assert order.payments[0].status is PaymentStatus.REFUNDED
        await deliver()
        mail = mails_to(mailer, "erika@example.de")[-1]
        assert "storniert" in mail.subject
        assert "erstatten" in mail.text
        assert "Auf Wunsch der Kundin" in mail.text

    async def test_unpaid_orders_are_given_up_after_a_day(
        self,
        carts: CartService,
        checkout: CheckoutService,
        orders: OrderService,
        clock: FixedClock,
        painted: UUID,
    ) -> None:
        first = (await place(checkout, carts, await filled_cart(carts, (painted, 1)))).details.order
        clock.advance(timedelta(hours=1))
        second = (
            await place(checkout, carts, await filled_cart(carts, (painted, 1)))
        ).details.order
        paid_id = await self.paid_order(carts, checkout, painted)
        clock.advance(PAYMENT_TIMEOUT - timedelta(minutes=30))
        assert await orders.cancel_overdue() == 1
        assert (await orders.get(first.id)).order.cancel_reason is CancelReason.PAYMENT_TIMEOUT
        assert (await orders.get(second.id)).order.status is OrderStatus.PENDING_PAYMENT
        assert (await orders.get(paid_id)).order.status is OrderStatus.PAID
        clock.advance(timedelta(hours=1))
        assert await orders.cancel_overdue() == 1
        assert await orders.cancel_overdue() == 0

    async def test_staff_search(
        self, carts: CartService, checkout: CheckoutService, orders: OrderService, painted: UUID
    ) -> None:
        paid_id = await self.paid_order(carts, checkout, painted)
        cart = await filled_cart(carts, (painted, 1))
        open_order = (await place(checkout, carts, cart, email="otto@example.de")).details.order
        assert [
            o.id
            for o in (await orders.search(statuses=None, text=None, cursor=None, limit=10)).items
        ] == [
            open_order.id,
            paid_id,
        ]
        only_paid = await orders.search(
            statuses=frozenset({OrderStatus.PAID}), text=None, cursor=None, limit=10
        )
        assert [o.id for o in only_paid.items] == [paid_id]
        by_mail = await orders.search(statuses=None, text="OTTO@", cursor=None, limit=10)
        assert [o.id for o in by_mail.items] == [open_order.id]
        by_number = await orders.search(
            statuses=None, text=open_order.number[-5:], cursor=None, limit=10
        )
        assert [o.id for o in by_number.items] == [open_order.id]
        assert (await orders.search(statuses=None, text="100%_", cursor=None, limit=10)).items == []
        with pytest.raises(OrderNotFoundError):
            await orders.get(uuid4())


class TestAdoption:
    async def test_verifying_an_address_adopts_its_guest_orders(
        self,
        carts: CartService,
        checkout: CheckoutService,
        orders: OrderService,
        identity: IdentityService,
        deliver: Deliver,
        mailer: InMemoryMailer,
        painted: UUID,
    ) -> None:
        cart = await filled_cart(carts, (painted, 1))
        guest = (await place(checkout, carts, cart, email="Neu@Example.de")).details.order
        cart = await filled_cart(carts, (painted, 1))
        other = (await place(checkout, carts, cart, email="jemand@example.de")).details.order

        account = await verified_customer(identity, deliver, mailer, "neu@example.de")
        assert (await orders.customer_orders(account, cursor=None, limit=10)).items == []
        await deliver()
        history = await orders.customer_orders(account, cursor=None, limit=10)
        assert [o.id for o in history.items] == [guest.id]
        assert (await orders.customer_order(account, guest.number)).order.id == guest.id
        with pytest.raises(OrderNotFoundError):
            await orders.customer_order(account, other.number)

    async def test_deleting_the_account_removes_the_address_book(
        self,
        addresses: AddressService,
        identity: IdentityService,
        deliver: Deliver,
        mailer: InMemoryMailer,
    ) -> None:
        account = await verified_customer(identity, deliver, mailer, "weg@example.de")
        await addresses.add(account, label="", address=ADDRESS, default=False)
        await identity.delete_account(account_id=account, password=PASSWORD)
        await deliver()
        assert await addresses.book(account) == []


class TestAddressBook:
    async def test_add_change_default_and_remove(
        self,
        addresses: AddressService,
        identity: IdentityService,
        deliver: Deliver,
        mailer: InMemoryMailer,
        clock: FixedClock,
    ) -> None:
        account = await verified_customer(identity, deliver, mailer, "buch@example.de")
        home = (await addresses.add(account, label="Zuhause", address=ADDRESS, default=False))[0]
        assert home.is_default
        clock.advance(timedelta(minutes=1))
        book = await addresses.add(
            account,
            label="Werkstatt",
            address=AddressInput("Erika", "Industriestraße 4", "38678", "Clausthal", "DE"),
            default=True,
        )
        assert [(a.label, a.is_default) for a in book] == [("Werkstatt", True), ("Zuhause", False)]
        book = await addresses.change(account, home.id, label=None, address=None, default=True)
        assert [(a.label, a.is_default) for a in book] == [("Zuhause", True), ("Werkstatt", False)]
        book = await addresses.change(account, home.id, label="Daheim", address=None, default=False)
        assert book[0].label == "Daheim"
        book = await addresses.remove(account, home.id)
        assert [(a.label, a.is_default) for a in book] == [("Werkstatt", True)]

    async def test_someone_elses_entry_is_not_found(
        self,
        addresses: AddressService,
        identity: IdentityService,
        deliver: Deliver,
        mailer: InMemoryMailer,
    ) -> None:
        owner = await verified_customer(identity, deliver, mailer, "a@example.de")
        stranger = await verified_customer(identity, deliver, mailer, "b@example.de")
        entry = (await addresses.add(owner, label="", address=ADDRESS, default=False))[0]
        with pytest.raises(AddressNotFoundError):
            await addresses.remove(stranger, entry.id)
        with pytest.raises(AddressNotFoundError):
            await addresses.change(stranger, entry.id, label="x", address=None, default=False)
