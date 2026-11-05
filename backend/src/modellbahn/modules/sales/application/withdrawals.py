"""The withdrawal function (§ 356a BGB, ADR 0020): take a declaration, act on it, show it.

A consumer withdraws by giving their name, the order number and an e-mail address for the
confirmation, then confirming. The declaration is stored with the time it came in; the
worker sends the confirmation of receipt and tells the shop (``handlers``).

What follows needs as little work as possible:

* before dispatch the shop cancels the order by itself, and the money goes back
  (:class:`WithdrawalAutomation`);
* after dispatch one click refunds once the return has arrived (``OrderService.refund``);
* a daily mail reminds the shop of refunds that fall due (:class:`RefundReminder`).
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Final
from uuid import UUID

import structlog

from modellbahn.modules.sales.application import mails
from modellbahn.modules.sales.application.common import UnitOfWorkFactory
from modellbahn.modules.sales.application.orders import OrderService
from modellbahn.modules.sales.application.ports import SalesUnitOfWork
from modellbahn.modules.sales.domain.events import WithdrawalReceived
from modellbahn.modules.sales.domain.model import Order, OrderStatus
from modellbahn.modules.sales.domain.withdrawals import ORDER_REFERENCE_MAX_LENGTH, Withdrawal
from modellbahn.platform.clock import Clock
from modellbahn.platform.mail import Mailer, compose
from modellbahn.platform.outbox import HandlerRegistry

REFUND_PERIOD: Final = timedelta(days=14)
"""The money goes back within 14 days of the withdrawal (§ 357 Abs. 1 BGB)."""
REMIND_BEFORE: Final = timedelta(days=4)
"""The reminder starts this long before a refund falls due, and goes on until it is done."""
REMIND_LOOKBACK: Final = timedelta(days=60)


class WithdrawalState(StrEnum):
    """Where a withdrawal stands, from its order; nothing about it is stored."""

    UNMATCHED = "unmatched"
    """Fits no order of the shop: someone checks it by hand (an eBay sale, a typo)."""
    CANCELLED = "cancelled"
    """The order was cancelled before dispatch; money that came in went back."""
    AWAITING_RETURN = "awaiting_return"
    """Shipped: the refund waits for the goods (or proof that they were sent)."""
    REFUNDED = "refunded"
    """Money went back after the return."""
    TO_CHECK = "to_check"
    """Only some articles, or an eBay order: staff decide what goes back."""


@dataclass(frozen=True, slots=True)
class WithdrawalView:
    withdrawal: Withdrawal
    state: WithdrawalState
    order_status: OrderStatus | None
    refunded_cents: int
    refund_due_at: datetime


def _state(withdrawal: Withdrawal, order: Order | None) -> WithdrawalState:
    if order is None:
        return WithdrawalState.UNMATCHED
    if order.status is OrderStatus.CANCELLED:
        return WithdrawalState.CANCELLED
    if order.from_marketplace:
        return WithdrawalState.TO_CHECK
    if order.refunded_cents > 0:
        return WithdrawalState.REFUNDED
    if order.status is OrderStatus.SHIPPED:
        return WithdrawalState.AWAITING_RETURN
    return WithdrawalState.TO_CHECK


async def _views(uow: SalesUnitOfWork, withdrawals: Sequence[Withdrawal]) -> list[WithdrawalView]:
    orders: dict[UUID, Order | None] = {}
    views = []
    for withdrawal in withdrawals:
        order = None
        if withdrawal.order_id is not None:
            if withdrawal.order_id not in orders:
                orders[withdrawal.order_id] = await uow.orders.get(withdrawal.order_id)
            order = orders[withdrawal.order_id]
        views.append(
            WithdrawalView(
                withdrawal=withdrawal,
                state=_state(withdrawal, order),
                order_status=order.status if order is not None else None,
                refunded_cents=order.refunded_cents if order is not None else 0,
                refund_due_at=withdrawal.received_at + REFUND_PERIOD,
            )
        )
    return views


_logger = structlog.get_logger(__name__)

RECENT_LIMIT_MAX = 200


class WithdrawalService:
    def __init__(self, *, uow_factory: UnitOfWorkFactory, clock: Clock) -> None:
        self._uow = uow_factory
        self._clock = clock

    async def declare(self, *, name: str, order_number: str, email: str, scope: str) -> Withdrawal:
        """Take a declaration of withdrawal; it counts from the moment it is stored."""
        async with self._uow() as uow:
            reference = order_number.strip().upper()
            order = (
                await uow.orders.get_by_number(reference)
                if 0 < len(reference) <= ORDER_REFERENCE_MAX_LENGTH
                else None
            )
            withdrawal, received = Withdrawal.declare(
                name=name,
                order_reference=order_number,
                email=email,
                scope=scope,
                order=order,
                now=self._clock.now(),
            )
            uow.withdrawals.add(withdrawal)
            uow.publish(received)
            await uow.commit()
        _logger.info(
            "sales.withdrawal.received",
            withdrawal_id=str(withdrawal.id),
            order=received.number,
            matched=withdrawal.order_id is not None,
        )
        return withdrawal

    async def recent(self, *, limit: int, order_id: UUID | None = None) -> list[WithdrawalView]:
        """The latest declarations with where they stand; those of one order if it is given."""
        async with self._uow() as uow:
            withdrawals = await uow.withdrawals.recent(
                limit=min(limit, RECENT_LIMIT_MAX), order_id=order_id
            )
            return await _views(uow, withdrawals)


class WithdrawalAutomation:
    """The worker acts on a withdrawal by itself where the law leaves nothing to judge."""

    def __init__(self, *, orders: OrderService) -> None:
        self._orders = orders

    def register(self, registry: HandlerRegistry) -> None:
        registry.register(WithdrawalReceived, self.settle)

    async def settle(self, event: WithdrawalReceived) -> None:
        outcome = await self._orders.settle_withdrawal(event.aggregate_id)
        _logger.info(
            "sales.withdrawal.settled", withdrawal_id=str(event.aggregate_id), outcome=outcome
        )


class RefundReminder:
    """A daily mail to the shop about refunds that fall due (a periodic job of the worker)."""

    def __init__(
        self,
        *,
        uow_factory: UnitOfWorkFactory,
        clock: Clock,
        mailer: Mailer,
        shop_email: str,
        public_base_url: str,
        shop_name: str,
        sender: Sequence[str] = (),
    ) -> None:
        self._uow = uow_factory
        self._clock = clock
        self._mailer = mailer
        self._shop_email = shop_email
        self._base_url = public_base_url
        self._shop_name = shop_name
        self._sender = tuple(sender)

    async def due(self) -> list[WithdrawalView]:
        """Withdrawals whose refund is open and due within a few days, or overdue."""
        now = self._clock.now()
        async with self._uow() as uow:
            views = await _views(uow, await uow.withdrawals.received_since(now - REMIND_LOOKBACK))
        return [
            view
            for view in views
            if view.state in {WithdrawalState.AWAITING_RETURN, WithdrawalState.TO_CHECK}
            and view.refund_due_at - now <= REMIND_BEFORE
        ]

    async def remind(self) -> int:
        """Mail the shop the open refunds that fall due; the number of them."""
        due = await self.due()
        if due and self._shop_email:
            content = mails.refund_reminder_mail(
                [(view.withdrawal, view.refund_due_at) for view in due],
                now=self._clock.now(),
                base_url=self._base_url,
            )
            await self._mailer.send(
                compose(
                    content, to=self._shop_email, shop_name=self._shop_name, sender=self._sender
                )
            )
            _logger.info("sales.refunds.reminded", count=len(due))
        return len(due)
