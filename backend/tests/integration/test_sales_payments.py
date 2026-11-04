"""Payments on SumUp's page against the database (ADR 0019), with a SumUp stand-in.

The stand-in (:class:`~tests.sales_support.FakeSumUp`) keeps the state SumUp would keep.
Tests move it like a customer would (``pay``), and check what the shop learns from it.
"""

from datetime import timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from modellbahn.modules.catalog.application.services import CatalogService, ProductDetails
from modellbahn.modules.media.application.services import MediaService
from modellbahn.modules.sales.application.cart import CartService
from modellbahn.modules.sales.application.checkout import CheckoutService
from modellbahn.modules.sales.application.common import UnitOfWorkFactory
from modellbahn.modules.sales.application.orders import OrderService
from modellbahn.modules.sales.application.payments import RECONCILE_AFTER, PaymentService
from modellbahn.modules.sales.application.ports import PaymentGateway
from modellbahn.modules.sales.domain.errors import (
    CheckoutClosedError,
    OrderNotFoundError,
    OrderNotPayableError,
    PaymentUnavailableError,
)
from modellbahn.modules.sales.domain.model import (
    PAYMENT_TIMEOUT,
    CancelReason,
    Order,
    OrderStatus,
    PaymentStatus,
)
from modellbahn.modules.sales.infrastructure.payments import ClosedPaymentGateway
from modellbahn.platform.clock import FixedClock
from tests.conftest import PUBLIC_BASE_URL, Deliver
from tests.integration.test_sales_service import event_types
from tests.media_support import InMemoryMediaStorage
from tests.sales_support import FakeSumUp, filled_cart, place, shop_product, variant_id


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
    product: ProductDetails = await shop_product(catalog, media, media_storage, deliver)
    return variant_id(product, "H0", "painted")


async def open_order(carts: CartService, checkout: CheckoutService, painted: UUID) -> Order:
    cart = await filled_cart(carts, (painted, 1))
    return (await place(checkout, carts, cart)).details.order


async def on_the_page(
    carts: CartService, checkout: CheckoutService, painted: UUID
) -> tuple[Order, str]:
    """An order whose customer was sent to SumUp's page; the order and the checkout."""
    order = await open_order(carts, checkout, painted)
    result = await checkout.pay(
        public_token=order.public_token, method="sumup", idempotency_key=uuid4()
    )
    pending = result.details.order.pending_payment
    assert pending is not None
    return result.details.order, pending.provider_ref


class TestPayingOnThePage:
    async def test_the_customer_pays_on_sumups_page(
        self,
        carts: CartService,
        checkout: CheckoutService,
        payments: PaymentService,
        sumup: FakeSumUp,
        engine: AsyncEngine,
        painted: UUID,
    ) -> None:
        order, reference = await on_the_page(carts, checkout, painted)
        (sent,) = sumup.requests
        assert sent.return_url == f"{PUBLIC_BASE_URL}/bestellung/{order.public_token}/bezahlen"
        assert (sent.order_number, sent.amount_cents) == (order.number, order.total_cents)
        assert sent.valid_until == order.payment_due_at
        payment = order.payments[0]
        assert (payment.id, payment.status) == (sent.payment_id, PaymentStatus.PENDING)
        assert payment.checkout_url == f"https://pay.sumup.test/{reference}"

        # Back without paying: the order still waits, with the same page.
        back = await payments.sync(order.public_token)
        assert back.order.status is OrderStatus.PENDING_PAYMENT
        again = await checkout.pay(
            public_token=order.public_token, method="sumup", idempotency_key=uuid4()
        )
        assert len(sumup.requests) == 1
        assert [p.provider_ref for p in again.details.order.payments] == [reference]

        sumup.pay(reference)
        paid = (await payments.sync(order.public_token)).order
        assert paid.status is OrderStatus.PAID
        assert paid.pending_payment is None
        assert (paid.payments[0].status, paid.payments[0].transaction_ref) == (
            PaymentStatus.CAPTURED,
            f"txn_{reference}",
        )
        await payments.sync(order.public_token)
        assert await event_types(engine) == ["sales.order.placed", "sales.order.paid"]
        with pytest.raises(OrderNotPayableError):
            await checkout.pay(
                public_token=order.public_token, method="sumup", idempotency_key=uuid4()
            )
        with pytest.raises(OrderNotFoundError):
            await payments.sync("nope")

    async def test_an_expired_page_makes_way_for_a_new_one(
        self, carts: CartService, checkout: CheckoutService, sumup: FakeSumUp, painted: UUID
    ) -> None:
        order, reference = await on_the_page(carts, checkout, painted)
        sumup.expire(reference)
        result = await checkout.pay(
            public_token=order.public_token, method="sumup", idempotency_key=uuid4()
        )
        first, second = result.details.order.payments
        assert (first.status, first.failure_code, first.checkout_url) == (
            PaymentStatus.FAILED,
            "expired",
            None,
        )
        assert (second.status, second.provider_ref) == (PaymentStatus.PENDING, "chk_2")

    async def test_paid_meanwhile_is_no_reason_for_another_page(
        self, carts: CartService, checkout: CheckoutService, sumup: FakeSumUp, painted: UUID
    ) -> None:
        order, reference = await on_the_page(carts, checkout, painted)
        sumup.pay(reference)
        result = await checkout.pay(
            public_token=order.public_token, method="sumup", idempotency_key=uuid4()
        )
        assert result.details.order.status is OrderStatus.PAID
        assert len(sumup.requests) == 1

    async def test_an_unreachable_sumup_records_nothing(
        self,
        carts: CartService,
        checkout: CheckoutService,
        orders: OrderService,
        payments: PaymentService,
        sumup: FakeSumUp,
        painted: UUID,
    ) -> None:
        order = await open_order(carts, checkout, painted)
        sumup.reachable = False
        with pytest.raises(PaymentUnavailableError):
            await checkout.pay(
                public_token=order.public_token, method="sumup", idempotency_key=uuid4()
            )
        assert (await orders.by_token(order.public_token)).order.payments == []

        sumup.reachable = True
        waiting, _ = await on_the_page(carts, checkout, painted)
        sumup.reachable = False
        with pytest.raises(PaymentUnavailableError):
            await payments.sync(waiting.public_token)
        assert (await orders.get(waiting.id)).order.pending_payment is not None


class TestNotifications:
    async def test_a_notification_only_names_what_to_ask_about(
        self,
        carts: CartService,
        checkout: CheckoutService,
        orders: OrderService,
        payments: PaymentService,
        sumup: FakeSumUp,
        painted: UUID,
    ) -> None:
        assert not await payments.notify("chk_unknown")
        order, reference = await on_the_page(carts, checkout, painted)
        # SumUp says something changed, but its API says the page is still open.
        assert await payments.notify(reference)
        assert (await orders.get(order.id)).order.status is OrderStatus.PENDING_PAYMENT
        sumup.pay(reference)
        sumup.reachable = False
        assert not await payments.notify(reference)
        sumup.reachable = True
        assert await payments.notify(reference)
        assert (await orders.get(order.id)).order.status is OrderStatus.PAID

    async def test_the_worker_asks_about_forgotten_pages(
        self,
        carts: CartService,
        checkout: CheckoutService,
        orders: OrderService,
        payments: PaymentService,
        sumup: FakeSumUp,
        clock: FixedClock,
        painted: UUID,
    ) -> None:
        order, reference = await on_the_page(carts, checkout, painted)
        sumup.pay(reference)
        # The customer usually comes back by themselves; the worker waits a minute.
        assert await payments.reconcile() == 0
        clock.advance(RECONCILE_AFTER)
        sumup.reachable = False
        assert await payments.reconcile() == 0
        sumup.reachable = True
        assert await payments.reconcile() == 1
        assert (await orders.get(order.id)).order.status is OrderStatus.PAID
        assert await payments.reconcile() == 0


class TestGivingUp:
    async def test_cancelling_closes_the_page(
        self,
        carts: CartService,
        checkout: CheckoutService,
        orders: OrderService,
        sumup: FakeSumUp,
        painted: UUID,
    ) -> None:
        order, reference = await on_the_page(carts, checkout, painted)
        cancelled = (await orders.cancel(order.id, note="")).order
        assert cancelled.status is OrderStatus.CANCELLED
        assert sumup.closed == [reference]
        assert (cancelled.payments[0].status, cancelled.payments[0].failure_code) == (
            PaymentStatus.FAILED,
            "cancelled",
        )
        assert sumup.refunds == []

    async def test_money_that_came_in_before_cancelling_goes_back(
        self,
        carts: CartService,
        checkout: CheckoutService,
        orders: OrderService,
        sumup: FakeSumUp,
        engine: AsyncEngine,
        painted: UUID,
    ) -> None:
        order, reference = await on_the_page(carts, checkout, painted)
        sumup.pay(reference)  # the shop has not heard of it yet
        cancelled = (await orders.cancel(order.id, note="Doppelt bestellt")).order
        assert cancelled.status is OrderStatus.CANCELLED
        assert cancelled.payments[0].status is PaymentStatus.REFUNDED
        assert sumup.refunds == [(f"txn_{reference}", order.total_cents)]
        assert await event_types(engine) == [
            "sales.order.placed",
            "sales.order.paid",
            "sales.order.cancelled",
        ]

    async def test_cancelling_waits_for_an_answer(
        self,
        carts: CartService,
        checkout: CheckoutService,
        orders: OrderService,
        sumup: FakeSumUp,
        painted: UUID,
    ) -> None:
        order, _ = await on_the_page(carts, checkout, painted)
        sumup.reachable = False
        with pytest.raises(PaymentUnavailableError):
            await orders.cancel(order.id, note="")
        assert (await orders.get(order.id)).order.status is OrderStatus.PENDING_PAYMENT

    async def test_money_after_the_order_was_given_up_goes_back(
        self,
        carts: CartService,
        checkout: CheckoutService,
        orders: OrderService,
        payments: PaymentService,
        sumup: FakeSumUp,
        clock: FixedClock,
        engine: AsyncEngine,
        painted: UUID,
    ) -> None:
        order, reference = await on_the_page(carts, checkout, painted)
        sumup.refuses_to_close = True
        await orders.cancel(order.id, note="")
        sumup.pay(reference)
        clock.advance(RECONCILE_AFTER)
        assert await payments.reconcile() == 1
        late = (await orders.get(order.id)).order
        assert late.status is OrderStatus.CANCELLED
        assert late.payments[0].status is PaymentStatus.REFUNDED
        assert sumup.refunds == [(f"txn_{reference}", order.total_cents)]
        assert "sales.order.paid" not in await event_types(engine)

    async def test_overdue_orders_keep_a_payment_made_at_the_last_minute(
        self,
        carts: CartService,
        checkout: CheckoutService,
        orders: OrderService,
        sumup: FakeSumUp,
        clock: FixedClock,
        painted: UUID,
    ) -> None:
        paid_late, paid_reference = await on_the_page(carts, checkout, painted)
        unpaid, unpaid_reference = await on_the_page(carts, checkout, painted)
        sumup.pay(paid_reference)
        clock.advance(PAYMENT_TIMEOUT)
        sumup.reachable = False
        assert await orders.cancel_overdue() == 0
        sumup.reachable = True
        assert await orders.cancel_overdue() == 1
        assert (await orders.get(paid_late.id)).order.status is OrderStatus.PAID
        given_up = (await orders.get(unpaid.id)).order
        assert given_up.cancel_reason is CancelReason.PAYMENT_TIMEOUT
        assert sumup.closed == [unpaid_reference]
        assert given_up.payments[0].failure_code == "cancelled"
        clock.advance(timedelta(hours=1))
        assert await orders.cancel_overdue() == 0


class TestClosedShop:
    async def test_no_provider_no_orders(
        self,
        carts: CartService,
        sales_uow: UnitOfWorkFactory,
        clock: FixedClock,
        painted: UUID,
    ) -> None:
        gateway = ClosedPaymentGateway()
        closed = CheckoutService(uow_factory=sales_uow, clock=clock, gateway=gateway)
        cart = await filled_cart(carts, (painted, 1))
        with pytest.raises(CheckoutClosedError):
            await place(closed, carts, cart)
        assert PaymentService(uow_factory=sales_uow, clock=clock, gateway=gateway).provider == "off"
