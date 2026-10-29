"""Outbox event handlers of the sales module; the worker runs them.

* Identity events: a verified address adopts the guest orders placed with it; a deleted
  account loses its address book (its orders stay for the retention periods).
* Order events: receipt, payment, dispatch and cancellation e-mails to the ordering address.
  Orders from a marketplace get none: their buyer hears from the marketplace.

Delivery is at least once. Adopting and removing are idempotent by nature; a notice
e-mail may in rare cases be sent twice.
"""

from collections.abc import Sequence

import structlog

from modellbahn.modules.identity.contracts.events import AccountDeleted, EmailVerified
from modellbahn.modules.sales.application import mails
from modellbahn.modules.sales.application.common import UnitOfWorkFactory
from modellbahn.modules.sales.domain.events import (
    OrderCancelled,
    OrderPaid,
    OrderPlaced,
    OrderShipped,
)
from modellbahn.modules.sales.domain.model import Order
from modellbahn.modules.site.contracts.next_fair import NextFair
from modellbahn.platform.clock import Clock
from modellbahn.platform.events import DomainEvent
from modellbahn.platform.mail import MailContent, Mailer, compose
from modellbahn.platform.outbox import HandlerRegistry

_logger = structlog.get_logger(__name__)


class SalesHandlers:
    def __init__(
        self,
        *,
        uow_factory: UnitOfWorkFactory,
        mailer: Mailer,
        clock: Clock,
        public_base_url: str,
        shop_name: str,
        sender: Sequence[str] = (),
    ) -> None:
        self._uow = uow_factory
        self._mailer = mailer
        self._clock = clock
        self._base_url = public_base_url
        self._shop_name = shop_name
        self._sender = tuple(sender)

    def register(self, registry: HandlerRegistry) -> None:
        """Subscribe the handlers to their events."""
        registry.register(EmailVerified, self.adopt_guest_orders)
        registry.register(AccountDeleted, self.remove_address_book)
        registry.register(OrderPlaced, self.send_receipt)
        registry.register(OrderPaid, self.send_confirmation)
        registry.register(OrderShipped, self.send_shipped_notice)
        registry.register(OrderCancelled, self.send_cancellation_notice)

    async def adopt_guest_orders(self, event: EmailVerified) -> None:
        """Guest orders with the now verified address join the customer's order history."""
        async with self._uow() as uow:
            email = await uow.accounts.verified_email(event.aggregate_id)
            if email is None:
                return
            now = self._clock.now()
            adopted = [
                order
                for order in await uow.orders.guest_orders_for(email)
                if order.adopt(event.aggregate_id, now)
            ]
            await uow.commit()
        if adopted:
            _logger.info(
                "sales.guest_orders.adopted",
                account_id=str(event.aggregate_id),
                orders=[order.number for order in adopted],
            )

    async def remove_address_book(self, event: AccountDeleted) -> None:
        async with self._uow() as uow:
            removed = await uow.addresses.delete_book(event.aggregate_id)
            await uow.commit()
        _logger.info(
            "sales.address_book.removed", account_id=str(event.aggregate_id), addresses=removed
        )

    async def send_receipt(self, event: OrderPlaced) -> None:
        order = await self._order(event)
        if order is not None:
            content = mails.received_mail(
                order,
                base_url=self._base_url,
                shop_name=self._shop_name,
                next_fair=await self._next_fair(),
            )
            await self._send(event, order, content)

    async def send_confirmation(self, event: OrderPaid) -> None:
        order = await self._order(event)
        if order is not None:
            content = mails.confirmation_mail(
                order, base_url=self._base_url, shop_name=self._shop_name
            )
            await self._send(event, order, content)

    async def send_shipped_notice(self, event: OrderShipped) -> None:
        order = await self._order(event)
        if order is not None:
            content = mails.shipped_mail(
                order, base_url=self._base_url, next_fair=await self._next_fair()
            )
            await self._send(event, order, content)

    async def send_cancellation_notice(self, event: OrderCancelled) -> None:
        order = await self._order(event)
        if order is not None:
            content = mails.cancelled_mail(order, base_url=self._base_url, refunded=event.refunded)
            await self._send(event, order, content)

    async def _next_fair(self) -> NextFair | None:
        today = self._clock.now().astimezone(mails.SHOP_TIME_ZONE).date()
        async with self._uow() as uow:
            return await uow.fairs.next_fair(today)

    async def _order(self, event: DomainEvent) -> Order | None:
        """The order to write to about the event; None if there is nobody to write to."""
        async with self._uow() as uow:
            order = await uow.orders.get(event.aggregate_id)
        if order is None:  # pragma: no cover - orders are never deleted
            _logger.warning("sales.mail.order_missing", event_id=str(event.event_id))
            return None
        if order.from_marketplace:
            return None
        return order

    async def _send(self, event: DomainEvent, order: Order, content: MailContent) -> None:
        await self._mailer.send(
            compose(content, to=order.email, shop_name=self._shop_name, sender=self._sender)
        )
        _logger.info(
            "sales.mail.sent",
            event_id=str(event.event_id),
            event_type=event.event_type,
            order=order.number,
        )
