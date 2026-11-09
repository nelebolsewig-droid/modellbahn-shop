"""Payment in advance by bank transfer against the database (ADR 0022).

The customer chooses the transfer on the payment page and gets the bank details by
e-mail; the staff book the money when it is in the account. Money that goes back is
transferred by hand: the customer is told so, the shop gets a to-do by e-mail.
"""

from datetime import timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from modellbahn.modules.catalog.application.services import CatalogService
from modellbahn.modules.media.application.services import MediaService
from modellbahn.modules.sales.application.cart import CartService
from modellbahn.modules.sales.application.checkout import CheckoutService
from modellbahn.modules.sales.application.common import UnitOfWorkFactory
from modellbahn.modules.sales.application.orders import OrderService
from modellbahn.modules.sales.application.ports import PaymentGateway
from modellbahn.modules.sales.domain.errors import InvalidFieldError, InvalidOrderStateError
from modellbahn.modules.sales.domain.model import (
    BANK_TRANSFER,
    BANK_TRANSFER_TIMEOUT,
    PAYMENT_TIMEOUT,
    CancelReason,
    Order,
    OrderStatus,
    PaymentStatus,
)
from modellbahn.platform.clock import FixedClock
from modellbahn.platform.mail import InMemoryMailer
from tests.conftest import PUBLIC_BASE_URL, SHOP_EMAIL, Deliver
from tests.integration.test_sales_service import event_types
from tests.media_support import InMemoryMediaStorage
from tests.sales_support import FakeSumUp, filled_cart, place, shop_product, variant_id
from tests.support import mails_to

CUSTOMER = "erika@example.de"


@pytest.fixture
def sumup() -> FakeSumUp:
    return FakeSumUp()


@pytest.fixture
def payment_gateway(sumup: FakeSumUp) -> PaymentGateway:
    return sumup


@pytest.fixture
async def painted(
    catalog: CatalogService,
    media: MediaService,
    media_storage: InMemoryMediaStorage,
    deliver: Deliver,
) -> UUID:
    return variant_id(await shop_product(catalog, media, media_storage, deliver), "H0", "painted")


async def by_transfer(carts: CartService, checkout: CheckoutService, painted: UUID) -> Order:
    cart = await filled_cart(carts, (painted, 1))
    order = (await place(checkout, carts, cart)).details.order
    result = await checkout.pay(
        public_token=order.public_token, method=BANK_TRANSFER, idempotency_key=uuid4()
    )
    return result.details.order


class TestChoosing:
    async def test_the_customer_gets_the_bank_details(
        self,
        carts: CartService,
        checkout: CheckoutService,
        sumup: FakeSumUp,
        deliver: Deliver,
        mailer: InMemoryMailer,
        engine: AsyncEngine,
        painted: UUID,
    ) -> None:
        order = await by_transfer(carts, checkout, painted)
        assert order.status is OrderStatus.PENDING_PAYMENT
        waiting = order.awaited_transfer
        assert waiting is not None
        assert (waiting.provider_ref, waiting.amount_cents) == (order.number, order.total_cents)
        assert order.payment_due_at == order.placed_at + BANK_TRANSFER_TIMEOUT
        assert sumup.requests == []  # SumUp never heard of it

        await deliver()
        received, details = mails_to(mailer, CUSTOMER)
        # Sent after the choice, the receipt names the transfer's deadline (CET, 10 days).
        assert "Bitte bezahle bis 01.11.2026, 11:00 Uhr" in received.text
        assert details.subject == f"So bezahlst du deine Bestellung {order.number} per Überweisung"
        assert "DE89 3704 0044 0532 0130 00" in details.text
        assert "Modellbahn-Shop Testkonto" in details.text
        assert order.number in details.text
        assert f"{PUBLIC_BASE_URL}/bestellung/{order.public_token}/bezahlen" in details.text
        assert await event_types(engine) == [
            "sales.order.placed",
            "sales.order.bank_transfer_chosen",
        ]

    async def test_asking_again_keeps_the_same_transfer(
        self, carts: CartService, checkout: CheckoutService, painted: UUID
    ) -> None:
        order = await by_transfer(carts, checkout, painted)
        for method in (BANK_TRANSFER, "sumup"):
            again = await checkout.pay(
                public_token=order.public_token, method=method, idempotency_key=uuid4()
            )
            assert [p.provider for p in again.details.order.payments] == [BANK_TRANSFER]

    async def test_from_sumups_page_to_a_transfer(
        self, carts: CartService, checkout: CheckoutService, sumup: FakeSumUp, painted: UUID
    ) -> None:
        cart = await filled_cart(carts, (painted, 1))
        order = (await place(checkout, carts, cart)).details.order
        await checkout.pay(public_token=order.public_token, method="sumup", idempotency_key=uuid4())
        switched = (
            await checkout.pay(
                public_token=order.public_token, method=BANK_TRANSFER, idempotency_key=uuid4()
            )
        ).details.order
        assert sumup.closed == ["chk_1"]
        assert [(p.provider, p.status) for p in switched.payments] == [
            ("sumup", PaymentStatus.FAILED),
            (BANK_TRANSFER, PaymentStatus.PENDING),
        ]

    async def test_paid_on_sumups_page_meanwhile_needs_no_transfer(
        self, carts: CartService, checkout: CheckoutService, sumup: FakeSumUp, painted: UUID
    ) -> None:
        cart = await filled_cart(carts, (painted, 1))
        order = (await place(checkout, carts, cart)).details.order
        await checkout.pay(public_token=order.public_token, method="sumup", idempotency_key=uuid4())
        sumup.pay("chk_1")
        result = await checkout.pay(
            public_token=order.public_token, method=BANK_TRANSFER, idempotency_key=uuid4()
        )
        assert result.details.order.status is OrderStatus.PAID
        assert not result.details.order.pays_by_transfer

    async def test_not_offered_without_a_bank_account(
        self,
        carts: CartService,
        sales_uow: UnitOfWorkFactory,
        clock: FixedClock,
        sumup: FakeSumUp,
        painted: UUID,
    ) -> None:
        without = CheckoutService(uow_factory=sales_uow, clock=clock, gateway=sumup)
        cart = await filled_cart(carts, (painted, 1))
        order = (await place(without, carts, cart)).details.order
        with pytest.raises(InvalidFieldError):
            await without.pay(
                public_token=order.public_token, method=BANK_TRANSFER, idempotency_key=uuid4()
            )


class TestBooking:
    async def test_the_staff_book_the_money_and_the_customer_hears_of_it(
        self,
        carts: CartService,
        checkout: CheckoutService,
        orders: OrderService,
        deliver: Deliver,
        mailer: InMemoryMailer,
        painted: UUID,
    ) -> None:
        order = await by_transfer(carts, checkout, painted)
        paid = (await orders.confirm_bank_transfer(order.id)).order
        assert paid.status is OrderStatus.PAID
        assert paid.payments[0].status is PaymentStatus.CAPTURED
        with pytest.raises(InvalidOrderStateError):
            await orders.confirm_bank_transfer(order.id)
        await deliver()
        assert mails_to(mailer, CUSTOMER)[-1].subject == (
            f"Zahlung eingegangen: Bestellung {order.number}"
        )

    async def test_no_transfer_after_ten_days_cancels_the_order(
        self,
        carts: CartService,
        checkout: CheckoutService,
        orders: OrderService,
        clock: FixedClock,
        deliver: Deliver,
        mailer: InMemoryMailer,
        painted: UUID,
    ) -> None:
        order = await by_transfer(carts, checkout, painted)
        clock.advance(PAYMENT_TIMEOUT + timedelta(hours=1))
        assert await orders.cancel_overdue() == 0
        clock.advance(BANK_TRANSFER_TIMEOUT)
        assert await orders.cancel_overdue() == 1
        given_up = (await orders.get(order.id)).order
        assert given_up.cancel_reason is CancelReason.PAYMENT_TIMEOUT
        assert given_up.awaited_transfer is None
        await deliver()
        cancelled = mails_to(mailer, CUSTOMER)[-1]
        assert "nicht innerhalb von zehn Tagen" in cancelled.text
        assert mails_to(mailer, SHOP_EMAIL) == []


class TestMoneyBack:
    async def test_cancelling_after_the_transfer_asks_the_shop_to_transfer_back(
        self,
        carts: CartService,
        checkout: CheckoutService,
        orders: OrderService,
        sumup: FakeSumUp,
        deliver: Deliver,
        mailer: InMemoryMailer,
        painted: UUID,
    ) -> None:
        order = await by_transfer(carts, checkout, painted)
        await orders.confirm_bank_transfer(order.id)
        cancelled = (await orders.cancel(order.id, note="Nicht mehr lieferbar")).order
        assert cancelled.status is OrderStatus.CANCELLED
        assert cancelled.payments[0].status is PaymentStatus.REFUNDED
        assert sumup.refunds == []
        await deliver()
        notice = mails_to(mailer, CUSTOMER)[-1]
        assert "auf das Konto zurück, von dem deine Überweisung kam" in notice.text
        (todo,) = mails_to(mailer, SHOP_EMAIL)
        assert todo.subject.startswith("Rücküberweisung: ")
        assert order.number in todo.subject
        assert f"{PUBLIC_BASE_URL}/admin/bestellungen/{order.id}" in todo.text

    async def test_a_part_after_a_return_is_transferred_back_too(
        self,
        carts: CartService,
        checkout: CheckoutService,
        orders: OrderService,
        sumup: FakeSumUp,
        deliver: Deliver,
        mailer: InMemoryMailer,
        painted: UUID,
    ) -> None:
        order = await by_transfer(carts, checkout, painted)
        await orders.confirm_bank_transfer(order.id)
        refunded = (await orders.refund(order.id, amount_cents=1000)).order
        assert refunded.refunded_cents == 1000
        assert sumup.refunds == []
        await deliver()
        assert "zurück, auf das Konto, von dem deine Überweisung kam" in (
            mails_to(mailer, CUSTOMER)[-1].text
        )
        (todo,) = mails_to(mailer, SHOP_EMAIL)
        assert "10,00\u00a0€" in todo.subject
