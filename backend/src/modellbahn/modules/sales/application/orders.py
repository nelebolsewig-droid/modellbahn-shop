"""Use cases around placed orders: status pages, order history, the admin area's actions."""

from uuid import UUID

import structlog

from modellbahn.modules.sales.application.common import (
    OrderDetails,
    OrderPage,
    UnitOfWorkFactory,
    order_details,
)
from modellbahn.modules.sales.application.cursors import decode_cursor, encode_cursor
from modellbahn.modules.sales.application.payments import close_page
from modellbahn.modules.sales.application.ports import (
    OrderCursor,
    OrderQuery,
    PaymentGateway,
    SalesUnitOfWork,
)
from modellbahn.modules.sales.domain.errors import (
    MarketplaceOrderError,
    OrderNotFoundError,
    OrderNotPickedError,
    PaymentUnavailableError,
    RefundNotPossibleError,
)
from modellbahn.modules.sales.domain.model import (
    CancelReason,
    Order,
    OrderStatus,
)
from modellbahn.platform.clock import Clock

_logger = structlog.get_logger(__name__)

OVERDUE_BATCH_SIZE = 100


class OrderService:
    def __init__(
        self, *, uow_factory: UnitOfWorkFactory, clock: Clock, gateway: PaymentGateway
    ) -> None:
        self._uow = uow_factory
        self._clock = clock
        self._gateway = gateway

    # --- Shop ---------------------------------------------------------------------------

    async def by_token(self, public_token: str) -> OrderDetails:
        """The order behind a status link; guests have nothing else to show who they are."""
        async with self._uow() as uow:
            order = await uow.orders.get_by_token(public_token)
            if order is None:
                raise OrderNotFoundError
            return await order_details(uow, order)

    async def customer_orders(
        self, account_id: UUID, *, cursor: str | None, limit: int
    ) -> OrderPage:
        """The customer's orders, including adopted guest orders, newest first."""
        return await self._page(
            OrderQuery(limit=limit, customer_account_id=account_id), cursor=cursor
        )

    async def customer_order(self, account_id: UUID, number: str) -> OrderDetails:
        """One of the customer's orders; someone else's answers like a missing one."""
        async with self._uow() as uow:
            order = await uow.orders.get_by_number(number)
            if order is None or order.customer_account_id != account_id:
                raise OrderNotFoundError
            return await order_details(uow, order)

    # --- Admin area ---------------------------------------------------------------------

    async def search(
        self,
        *,
        statuses: frozenset[OrderStatus] | None,
        text: str | None,
        cursor: str | None,
        limit: int,
    ) -> OrderPage:
        cleaned = text.strip() if text else None
        return await self._page(
            OrderQuery(limit=limit, statuses=statuses, text=cleaned or None), cursor=cursor
        )

    async def get(self, order_id: UUID) -> OrderDetails:
        async with self._uow() as uow:
            order = await uow.orders.get(order_id)
            if order is None:
                raise OrderNotFoundError
            return await order_details(uow, order)

    async def ship(self, order_id: UUID, *, carrier: str, tracking_number: str) -> OrderDetails:
        """Ship a paid order whose pieces are all picked (the workshop scanned each one).

        Without a shipment number given, the order's label in force supplies carrier and
        number (ADR 0023), so they reach the customer's e-mail.
        """
        async with self._uow() as uow:
            order = await self._locked(uow, order_id)
            if not tracking_number.strip():
                label = await uow.labels.active_for(order.id)
                if label is not None:
                    carrier, tracking_number = (
                        carrier.strip() or label.carrier,
                        label.shipment_number,
                    )
            if order.status is OrderStatus.PAID:
                progress = await uow.inventory.pick_progress(order.id)
                if not progress.is_complete:
                    raise OrderNotPickedError(picked=progress.picked, total=progress.total)
            uow.publish(
                order.ship(carrier=carrier, tracking_number=tracking_number, now=self._clock.now())
            )
            await uow.commit()
            return await order_details(uow, order)

    async def cancel(
        self, order_id: UUID, *, note: str, refunded_by_hand: bool = False
    ) -> OrderDetails:
        """Cancel an order that has not been shipped; a payment that came in is refunded.

        ``refunded_by_hand`` says the staff gave the money back in the provider's own
        account already (say, after the provider refused the refund here): the shop then
        records the refund without asking the provider a second time.

        A marketplace order is cancelled on the marketplace, which refunds the buyer; the
        shop follows when it reads the cancellation from there.
        """
        async with self._uow() as uow:
            order = await self._locked(uow, order_id)
            if order.from_marketplace:
                raise MarketplaceOrderError
            # The customer may be on the provider's page right now. Money that comes in
            # there makes the order paid, and the cancellation below refunds it.
            await close_page(uow, order, self._gateway, self._clock)
            await self._cancel(
                uow, order, CancelReason.BY_SHOP, note, refunded_by_hand=refunded_by_hand
            )
            await uow.commit()
            return await order_details(uow, order)

    async def confirm_bank_transfer(self, order_id: UUID) -> OrderDetails:
        """The customer's transfer is in the shop's account: the order is paid (ADR 0022).

        The staff book it by hand after looking at the account; the customer gets the
        usual confirmation, and picking starts as after any payment.
        """
        async with self._uow() as uow:
            order = await self._locked(uow, order_id)
            uow.publish(*order.confirm_bank_transfer(self._clock.now()))
            await uow.commit()
            _logger.info("sales.order.transfer_received", order=order.number)
            return await order_details(uow, order)

    async def refund(
        self, order_id: UUID, *, amount_cents: int, refunded_by_hand: bool = False
    ) -> OrderDetails:
        """Give money back for a paid or shipped order, e.g. once a return has arrived.

        The provider refunds first; if it fails, nothing is recorded. With
        ``refunded_by_hand`` the staff refunded in the provider's account themselves and
        the shop only records it. The customer gets an e-mail (``sales.order.refunded``).
        A whole cancellation before dispatch is :meth:`cancel`.
        """
        async with self._uow() as uow:
            order = await self._locked(uow, order_id)
            if order.from_marketplace:
                raise MarketplaceOrderError
            payment = order.captured_payment
            if payment is None or not 0 < amount_cents <= order.refundable_cents:
                raise RefundNotPossibleError(order.refundable_cents)
            # A bank transfer has no provider to refund it: the money goes back by hand.
            by_hand = refunded_by_hand or payment.by_transfer
            if not by_hand:
                await self._gateway.refund(refund_ref=payment.refund_ref, amount_cents=amount_cents)
            uow.publish(order.refund(amount_cents, self._clock.now()))
            await uow.commit()
            _logger.info(
                "sales.order.refunded",
                order=order.number,
                amount_cents=amount_cents,
                by_hand=by_hand,
            )
            return await order_details(uow, order)

    async def settle_withdrawal(self, withdrawal_id: UUID) -> str:
        """What a withdrawal makes the shop do by itself (ADR 0020); the outcome, for the log.

        A withdrawal of a whole order before dispatch cancels it, and a payment that came in
        goes back. After dispatch the shop waits for the return (:meth:`refund`); a partial
        withdrawal, one that fits no order and an eBay order are for staff to judge.
        """
        async with self._uow() as uow:
            withdrawal = await uow.withdrawals.get(withdrawal_id)
            if withdrawal is None or withdrawal.order_id is None:
                return "unmatched"
            if not withdrawal.whole_order:
                return "partial"
            order = await self._locked(uow, withdrawal.order_id)
            if order.from_marketplace:
                return "marketplace"
            if order.status not in {OrderStatus.PENDING_PAYMENT, OrderStatus.PAID}:
                return str(order.status)
            # Raises PaymentUnavailableError if the provider cannot be asked: the outbox
            # tries again.
            await close_page(uow, order, self._gateway, self._clock)
            await self._cancel(uow, order, CancelReason.WITHDRAWN, "")
            await uow.commit()
        _logger.info("sales.withdrawal.cancelled_order", order=order.number)
        return "cancelled"

    async def cancel_overdue(self) -> int:
        """Give up orders whose payment did not come in by their deadline (a periodic job)."""
        now = self._clock.now()
        async with self._uow() as uow:
            ids = await uow.orders.overdue_ids(now, OVERDUE_BATCH_SIZE)
        cancelled = 0
        for order_id in ids:
            async with self._uow() as uow:
                order = await uow.orders.get(order_id, for_update=True)
                # Paid in the meantime, or cancelled by someone: nothing to do.
                if order is None or not order.is_overdue(self._clock.now()):
                    continue
                try:
                    await close_page(uow, order, self._gateway, self._clock)
                except PaymentUnavailableError:
                    # The next round asks again; nobody pays on an expired page meanwhile.
                    _logger.warning("sales.orders.overdue_unanswered", order=order.number)
                    continue
                # Paid at the last minute on the provider's page: the order stays.
                if order.is_overdue(self._clock.now()):
                    await self._cancel(uow, order, CancelReason.PAYMENT_TIMEOUT, "")
                    cancelled += 1
                await uow.commit()
        if cancelled:
            _logger.info("sales.orders.overdue_cancelled", count=cancelled)
        return cancelled

    async def _cancel(
        self,
        uow: SalesUnitOfWork,
        order: Order,
        reason: CancelReason,
        note: str,
        *,
        refunded_by_hand: bool = False,
    ) -> None:
        payment = order.captured_payment
        if payment is not None and order.status is OrderStatus.PAID and not order.from_marketplace:
            if refunded_by_hand or payment.by_transfer:
                # In the provider's account by the staff, or back by bank transfer.
                _logger.info(
                    "sales.order.refunded_by_hand",
                    order=order.number,
                    amount_cents=payment.refundable_cents,
                    by_transfer=payment.by_transfer,
                )
            else:
                # Refund first: if the provider fails, the order stays as it is. What went
                # back already (part of a withdrawal) is not refunded twice.
                await self._gateway.refund(
                    refund_ref=payment.refund_ref, amount_cents=payment.refundable_cents
                )
        uow.publish(order.cancel(reason=reason, note=note, now=self._clock.now()))

    async def _locked(self, uow: SalesUnitOfWork, order_id: UUID) -> Order:
        order = await uow.orders.get(order_id, for_update=True)
        if order is None:
            raise OrderNotFoundError
        return order

    async def _page(self, query: OrderQuery, *, cursor: str | None) -> OrderPage:
        after = decode_cursor(cursor) if cursor else None
        page_query = OrderQuery(
            limit=query.limit + 1,
            customer_account_id=query.customer_account_id,
            statuses=query.statuses,
            text=query.text,
            after=after,
        )
        async with self._uow() as uow:
            orders = await uow.orders.search(page_query)
        items = orders[: query.limit]
        next_cursor = None
        if len(orders) > query.limit:
            last = items[-1]
            next_cursor = encode_cursor(OrderCursor(placed_at=last.placed_at, id=last.id))
        return OrderPage(items=items, next_cursor=next_cursor)
