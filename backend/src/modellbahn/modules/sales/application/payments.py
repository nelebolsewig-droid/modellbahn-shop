"""Payments on the provider's page (ADR 0019): learn their outcome, whoever asks.

A SumUp payment is pending while the customer pays on SumUp's page. Three things can
tell the shop that something happened, and none of them is trusted on its own:

* the customer comes back to the shop (``sync``);
* SumUp posts the checkout's id to the shop (``notify``);
* the worker looks at every pending payment that is older than a minute (``reconcile``).

Each of them asks the provider for the payment's state and books that (:func:`settle`).
Money that comes in after the order was given up goes straight back.
"""

from datetime import timedelta
from typing import Final

import structlog

from modellbahn.modules.sales.application.common import (
    OrderDetails,
    UnitOfWorkFactory,
    order_details,
)
from modellbahn.modules.sales.application.ports import PaymentGateway, SalesUnitOfWork
from modellbahn.modules.sales.domain.errors import OrderNotFoundError, PaymentUnavailableError
from modellbahn.modules.sales.domain.model import (
    Order,
    PaymentOutcome,
    PaymentProgress,
    PaymentStatus,
)
from modellbahn.platform.clock import Clock

RECONCILE_AFTER: Final = timedelta(minutes=1)
"""A payment this old is checked by the worker (the customer usually comes back sooner)."""
RECONCILE_BATCH_SIZE: Final = 50

_logger = structlog.get_logger(__name__)


async def settle(uow: SalesUnitOfWork, order: Order, gateway: PaymentGateway, clock: Clock) -> None:
    """Book what the provider says about the order's pending payment (the order is locked).

    Raises ``PaymentUnavailableError`` if the provider cannot be asked; nothing changes then.
    """
    payment = order.pending_payment
    if payment is None or payment.provider != gateway.provider:
        return
    outcome = await gateway.outcome(payment.provider_ref)
    uow.publish(*order.settle_payment(payment, outcome, clock.now()))
    stray = order.stray_payment
    if stray is not None:
        # Paid at the last minute, or the answer came late: the order is gone, the money
        # goes back. Refund first; if that fails, the payment stays captured and the next
        # round tries again.
        await gateway.refund(refund_ref=stray.refund_ref, amount_cents=stray.amount_cents)
        stray.refund(clock.now())
        _logger.warning("sales.payment.refunded_after_cancel", order=order.number)


async def close_page(
    uow: SalesUnitOfWork, order: Order, gateway: PaymentGateway, clock: Clock
) -> None:
    """Before an order is given up: close its payment page, or learn what happened there.

    If the provider closes the page, nothing can be paid there any more. If it refuses,
    the customer may have paid just now: the provider's answer is booked, and money that
    came in makes the order paid (the caller decides whether it still cancels and refunds).
    Raises ``PaymentUnavailableError`` if the provider cannot be asked.
    """
    payment = order.pending_payment
    if payment is None or payment.provider != gateway.provider:
        return
    try:
        await gateway.abandon(payment.provider_ref)
    except PaymentUnavailableError:
        await settle(uow, order, gateway, clock)
        return
    closed = PaymentOutcome(progress=PaymentProgress.FAILED, failure_code="cancelled")
    uow.publish(*order.settle_payment(payment, closed, clock.now()))


class PaymentService:
    def __init__(self, *, uow_factory: UnitOfWorkFactory, clock: Clock, gateway: PaymentGateway):
        self._uow = uow_factory
        self._clock = clock
        self._gateway = gateway

    @property
    def provider(self) -> str:
        """Who takes the payments (``sumup``, ``mock``, ``off``)."""
        return self._gateway.provider

    async def sync(self, public_token: str) -> OrderDetails:
        """The customer is back from the provider's page: ask it how the payment went."""
        async with self._uow() as uow:
            order = await uow.orders.get_by_token(public_token, for_update=True)
            if order is None:
                raise OrderNotFoundError
            await settle(uow, order, self._gateway, self._clock)
            await uow.commit()
            return await order_details(uow, order)

    async def notify(self, provider_ref: str) -> bool:
        """The provider says a payment changed; True if it is one of ours and was checked.

        The notification carries no proof, so it only names what to ask the provider about.
        """
        async with self._uow() as uow:
            order_id = await uow.orders.id_by_payment(self._gateway.provider, provider_ref)
            if order_id is None:
                return False
            order = await uow.orders.get(order_id, for_update=True)
            if order is None:  # pragma: no cover - orders are never deleted
                return False
            try:
                await settle(uow, order, self._gateway, self._clock)
            except PaymentUnavailableError:
                # The worker's next round asks again.
                _logger.warning("sales.payment.notify_unanswered", order=order.number)
                return False
            await uow.commit()
            return True

    async def reconcile(self) -> int:
        """Ask the provider about pending payments that nobody has asked about (a periodic job)."""
        async with self._uow() as uow:
            ids = await uow.orders.pending_payment_ids(
                self._gateway.provider, self._clock.now() - RECONCILE_AFTER, RECONCILE_BATCH_SIZE
            )
        settled = 0
        for order_id in ids:
            async with self._uow() as uow:
                order = await uow.orders.get(order_id, for_update=True)
                payment = order.pending_payment if order is not None else None
                if order is None or payment is None:
                    continue
                try:
                    await settle(uow, order, self._gateway, self._clock)
                except PaymentUnavailableError:
                    _logger.warning("sales.payment.reconcile_unanswered", order=order.number)
                    continue
                if payment.status is not PaymentStatus.PENDING:
                    settled += 1
                await uow.commit()
        if settled:
            _logger.info("sales.payment.reconciled", count=settled)
        return settled
