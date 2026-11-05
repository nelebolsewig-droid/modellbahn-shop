"""The withdrawal function against the database (§ 356a BGB, ADR 0020).

A declaration is stored with the time it came in; the worker confirms it to the consumer
and tells the shop. Unknown numbers are taken all the same.
"""

from datetime import timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from modellbahn.modules.catalog.application.services import CatalogService
from modellbahn.modules.identity.application.services import IdentityService
from modellbahn.modules.inventory.application.allocation import AllocationService
from modellbahn.modules.inventory.application.locations import LocationService
from modellbahn.modules.inventory.application.scanning import ScanService
from modellbahn.modules.inventory.application.units import UnitService
from modellbahn.modules.media.application.services import MediaService
from modellbahn.modules.sales.application.cart import CartService
from modellbahn.modules.sales.application.checkout import CheckoutService
from modellbahn.modules.sales.application.common import UnitOfWorkFactory
from modellbahn.modules.sales.application.orders import OrderService
from modellbahn.modules.sales.application.withdrawals import (
    RefundReminder,
    WithdrawalService,
    WithdrawalState,
)
from modellbahn.modules.sales.domain.errors import InvalidFieldError, RefundNotPossibleError
from modellbahn.modules.sales.domain.model import CancelReason, Order, OrderStatus, PaymentStatus
from modellbahn.platform.clock import FixedClock
from modellbahn.platform.mail import InMemoryMailer
from tests.conftest import PUBLIC_BASE_URL, SHOP_EMAIL, Deliver
from tests.integration.test_sales_service import event_types
from tests.inventory_support import pick_everything, staff_member, stock_up
from tests.media_support import InMemoryMediaStorage
from tests.sales_support import filled_cart, place, shop_product, variant_id
from tests.support import mails_to


@pytest.fixture
async def painted(
    catalog: CatalogService,
    media: MediaService,
    media_storage: InMemoryMediaStorage,
    deliver: Deliver,
) -> UUID:
    product = await shop_product(catalog, media, media_storage, deliver)
    return variant_id(product, "H0", "painted")


@pytest.fixture
async def order(
    painted: UUID, deliver: Deliver, carts: CartService, checkout: CheckoutService
) -> Order:
    cart = await filled_cart(carts, (painted, 1))
    placed = (await place(checkout, carts, cart)).details.order
    await deliver()  # the order's own mails go out first
    return placed


class TestWithdrawalFunction:
    async def test_a_declaration_is_confirmed_and_reported(
        self,
        withdrawals: WithdrawalService,
        order: Order,
        deliver: Deliver,
        mailer: InMemoryMailer,
        engine: AsyncEngine,
        clock: FixedClock,
    ) -> None:
        received = await withdrawals.declare(
            name="Erika Mustermann",
            order_number=order.number.lower(),
            email="ERIKA@example.de",
            scope="",
        )
        assert received.order_id == order.id
        assert received.received_at == clock.now()
        assert "sales.withdrawal.received" in await event_types(engine)

        await deliver()
        (receipt,) = mails_to(mailer, "ERIKA@example.de")
        assert receipt.subject == f"Eingangsbestätigung: dein Widerruf zu Bestellung {order.number}"
        assert "Widerrufen: die ganze Bestellung." in receipt.text
        assert "Die Kosten der Rücksendung trägst du." in receipt.text
        (notice,) = mails_to(mailer, SHOP_EMAIL)
        assert notice.subject == f"Widerruf eingegangen: {order.number}"
        assert f"{PUBLIC_BASE_URL}/admin/bestellungen/{order.id}" in notice.text

    async def test_an_unknown_number_is_taken_all_the_same(
        self,
        withdrawals: WithdrawalService,
        order: Order,
        deliver: Deliver,
        mailer: InMemoryMailer,
    ) -> None:
        # Right number, other address: no order is named, and the answer is the same.
        other = await withdrawals.declare(
            name="Max Muster", order_number=order.number, email="max@example.de", scope=""
        )
        unknown = await withdrawals.declare(
            name="Max Muster",
            order_number="MB-1999-00001",
            email="max@example.de",
            scope="den Prellbock",
        )
        assert (other.order_id, unknown.order_id) == (None, None)
        await deliver()
        assert len(mails_to(mailer, "max@example.de")) == 2
        notices = mails_to(mailer, SHOP_EMAIL)
        assert all("passt keine Bestellung" in mail.text for mail in notices)
        assert len(notices) == 2

    async def test_staff_see_the_latest_first_and_per_order(
        self, withdrawals: WithdrawalService, order: Order, clock: FixedClock
    ) -> None:
        first = await withdrawals.declare(
            name="Erika Mustermann", order_number=order.number, email=order.email, scope=""
        )
        clock.advance(timedelta(minutes=5))
        later = await withdrawals.declare(
            name="Max Muster", order_number="MB-1999-00001", email="max@example.de", scope=""
        )
        recent = await withdrawals.recent(limit=10)
        assert [view.withdrawal.id for view in recent] == [later.id, first.id]
        assert [view.state for view in recent] == [
            WithdrawalState.UNMATCHED,
            WithdrawalState.TO_CHECK,  # the order still waits for its payment
        ]
        assert recent[1].refund_due_at == first.received_at + timedelta(days=14)
        for_order = await withdrawals.recent(limit=10, order_id=order.id)
        assert [view.withdrawal.id for view in for_order] == [first.id]
        assert await withdrawals.recent(limit=10, order_id=UUID(int=0)) == []

    async def test_what_cannot_be_confirmed_is_refused(
        self, withdrawals: WithdrawalService
    ) -> None:
        with pytest.raises(InvalidFieldError):
            await withdrawals.declare(
                name="Erika", order_number="MB-2026-00042", email="keine-adresse", scope=""
            )
        # An absurdly long number is no order of ours, and still not a crash.
        with pytest.raises(InvalidFieldError):
            await withdrawals.declare(
                name="Erika", order_number="M" * 41, email="erika@example.de", scope=""
            )
        assert await withdrawals.recent(limit=10) == []


async def paid(carts: CartService, checkout: CheckoutService, variant: UUID) -> Order:
    cart = await filled_cart(carts, (variant, 1))
    order = (await place(checkout, carts, cart)).details.order
    result = await checkout.pay(
        public_token=order.public_token, method="succeeds", idempotency_key=uuid4()
    )
    return result.details.order


class TestWhatTheShopDoesByItself:
    async def test_before_payment_the_order_is_cancelled(
        self,
        withdrawals: WithdrawalService,
        orders: OrderService,
        order: Order,
        deliver: Deliver,
        mailer: InMemoryMailer,
    ) -> None:
        await withdrawals.declare(
            name="Erika Mustermann", order_number=order.number, email=order.email, scope=""
        )
        await deliver()  # confirmation, notice, and the cancellation
        cancelled = (await orders.get(order.id)).order
        assert (cancelled.status, cancelled.cancel_reason) == (
            OrderStatus.CANCELLED,
            CancelReason.WITHDRAWN,
        )
        await deliver()
        mail = mails_to(mailer, order.email)[-1]
        assert mail.subject == f"Deine Bestellung {order.number} wurde storniert"
        assert "widerrufen, bevor wir sie verschickt haben" in mail.text

    async def test_a_paid_order_is_cancelled_and_refunded(
        self,
        withdrawals: WithdrawalService,
        orders: OrderService,
        carts: CartService,
        checkout: CheckoutService,
        deliver: Deliver,
        painted: UUID,
    ) -> None:
        order = await paid(carts, checkout, painted)
        await withdrawals.declare(
            name="Erika Mustermann", order_number=order.number, email=order.email, scope=""
        )
        await deliver()
        cancelled = (await orders.get(order.id)).order
        assert cancelled.status is OrderStatus.CANCELLED
        payment = cancelled.payments[0]
        assert (payment.status, payment.refunded_cents) == (
            PaymentStatus.REFUNDED,
            order.total_cents,
        )
        (view,) = await withdrawals.recent(limit=5)
        assert view.state is WithdrawalState.CANCELLED

    async def test_some_articles_only_are_for_staff_to_judge(
        self,
        withdrawals: WithdrawalService,
        orders: OrderService,
        carts: CartService,
        checkout: CheckoutService,
        deliver: Deliver,
        painted: UUID,
    ) -> None:
        order = await paid(carts, checkout, painted)
        await withdrawals.declare(
            name="Erika Mustermann",
            order_number=order.number,
            email=order.email,
            scope="nur die Lackierung",
        )
        await deliver()
        assert (await orders.get(order.id)).order.status is OrderStatus.PAID
        (view,) = await withdrawals.recent(limit=5)
        assert view.state is WithdrawalState.TO_CHECK


class TestRefundAfterReturn:
    async def shipped(
        self,
        carts: CartService,
        checkout: CheckoutService,
        orders: OrderService,
        deliver: Deliver,
        painted: UUID,
        identity: IdentityService,
        locations: LocationService,
        units: UnitService,
        scans: ScanService,
        allocation: AllocationService,
    ) -> Order:
        await stock_up(locations, units, painted)
        order = await paid(carts, checkout, painted)
        await deliver()
        await pick_everything(scans, allocation, order.id, await staff_member(identity))
        return (await orders.ship(order.id, carrier="DHL", tracking_number="0034")).order

    async def test_after_dispatch_one_click_refunds_and_reminders_stop(
        self,
        withdrawals: WithdrawalService,
        orders: OrderService,
        carts: CartService,
        checkout: CheckoutService,
        deliver: Deliver,
        mailer: InMemoryMailer,
        clock: FixedClock,
        sales_uow: UnitOfWorkFactory,
        painted: UUID,
        identity: IdentityService,
        locations: LocationService,
        units: UnitService,
        scans: ScanService,
        allocation: AllocationService,
    ) -> None:
        order = await self.shipped(
            carts, checkout, orders, deliver, painted, identity, locations, units, scans, allocation
        )
        await withdrawals.declare(
            name="Erika Mustermann", order_number=order.number, email=order.email, scope=""
        )
        await deliver()
        # Shipped: the shop waits for the return.
        assert (await orders.get(order.id)).order.status is OrderStatus.SHIPPED
        (view,) = await withdrawals.recent(limit=5)
        assert view.state is WithdrawalState.AWAITING_RETURN

        reminder = RefundReminder(
            uow_factory=sales_uow,
            clock=clock,
            mailer=mailer,
            shop_email=SHOP_EMAIL,
            public_base_url=PUBLIC_BASE_URL,
            shop_name="Gleiswerk",
        )
        assert await reminder.remind() == 0  # not due for a while
        clock.advance(timedelta(days=11))
        assert await reminder.remind() == 1
        notice = mails_to(mailer, SHOP_EMAIL)[-1]
        assert notice.subject == "Erinnerung: Eine Erstattung nach Widerruf fällig"
        assert order.number in notice.text

        with pytest.raises(RefundNotPossibleError):
            await orders.refund(order.id, amount_cents=order.total_cents + 1)
        part = (await orders.refund(order.id, amount_cents=4990)).order
        assert part.refunded_cents == 4990
        assert part.payments[0].status is PaymentStatus.CAPTURED
        rest = (await orders.refund(order.id, amount_cents=order.total_cents - 4990)).order
        assert rest.payments[0].status is PaymentStatus.REFUNDED
        with pytest.raises(RefundNotPossibleError):
            await orders.refund(order.id, amount_cents=1)

        await deliver()
        refund_mails = [
            mail for mail in mails_to(mailer, order.email) if mail.subject.startswith("Erstattung")
        ]
        assert len(refund_mails) == 2
        assert "49,90" in refund_mails[0].text
        (view,) = await withdrawals.recent(limit=5)
        assert (view.state, view.refunded_cents) == (WithdrawalState.REFUNDED, order.total_cents)
        assert await reminder.remind() == 0
