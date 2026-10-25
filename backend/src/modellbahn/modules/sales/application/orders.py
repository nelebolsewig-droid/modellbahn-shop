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
from modellbahn.modules.sales.application.ports import (
    OrderCursor,
    OrderQuery,
    PaymentGateway,
    SalesUnitOfWork,
)
from modellbahn.modules.sales.domain.errors import OrderNotFoundError
from modellbahn.modules.sales.domain.model import (
    PAYMENT_TIMEOUT,
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
        async with self._uow() as uow:
            order = await self._locked(uow, order_id)
            uow.publish(
                order.ship(carrier=carrier, tracking_number=tracking_number, now=self._clock.now())
            )
            await uow.commit()
            return await order_details(uow, order)

    async def cancel(self, order_id: UUID, *, note: str) -> OrderDetails:
        """Cancel an order that has not been shipped; a payment that came in is refunded."""
        async with self._uow() as uow:
            order = await self._locked(uow, order_id)
            await self._cancel(uow, order, CancelReason.BY_SHOP, note)
            await uow.commit()
            return await order_details(uow, order)

    async def cancel_overdue(self) -> int:
        """Give up orders whose payment has not come in within 24 hours (a periodic job)."""
        now = self._clock.now()
        async with self._uow() as uow:
            ids = await uow.orders.overdue_ids(now - PAYMENT_TIMEOUT, OVERDUE_BATCH_SIZE)
        cancelled = 0
        for order_id in ids:
            async with self._uow() as uow:
                order = await uow.orders.get(order_id, for_update=True)
                # Paid in the meantime, or cancelled by someone: nothing to do.
                if order is None or not order.is_overdue(self._clock.now()):
                    continue
                await self._cancel(uow, order, CancelReason.PAYMENT_TIMEOUT, "")
                await uow.commit()
                cancelled += 1
        if cancelled:
            _logger.info("sales.orders.overdue_cancelled", count=cancelled)
        return cancelled

    async def _cancel(
        self, uow: SalesUnitOfWork, order: Order, reason: CancelReason, note: str
    ) -> None:
        payment = order.captured_payment
        if payment is not None and order.status is OrderStatus.PAID:
            # Refund first: if the provider fails, the order stays as it is.
            await self._gateway.refund(
                provider_ref=payment.provider_ref, amount_cents=payment.amount_cents
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
