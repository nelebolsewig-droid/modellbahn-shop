"""Outbox event handlers of the sales module; the worker runs them.

* Identity events: a verified address adopts the guest orders placed with it; a deleted
  account loses its address book (its orders stay for the retention periods).
* Order events: receipt, payment, dispatch, cancellation and refund e-mails to the ordering
  address.
  Orders from a marketplace get none: their buyer hears from the marketplace.
* Withdrawals: the confirmation of receipt to the consumer (§ 356a BGB) and a notice to
  the shop's own address.
* Backorders: a paid order whose checkout saw everything on the shelves learns the lead
  time of the pieces made for it after all, and its customer hears so once (ADR 0029).
* Print jobs: when a plate for its pieces starts printing, a paid order notes so and its
  customer hears so once (ADR 0034).

Delivery is at least once. Adopting and removing are idempotent by nature; an order
learns a late lead time once, however many of its pieces are backordered; a notice e-mail
may in rare cases be sent twice.
"""

from collections.abc import Sequence

import structlog

from modellbahn.modules.identity.contracts.events import AccountDeleted, EmailVerified
from modellbahn.modules.inventory.contracts.events import AllocationBackordered
from modellbahn.modules.manufacturing.contracts.events import PrintJobChanged
from modellbahn.modules.sales.application import mails
from modellbahn.modules.sales.application.common import UnitOfWorkFactory
from modellbahn.modules.sales.application.invoices import InvoiceService
from modellbahn.modules.sales.domain.events import (
    BankTransferChosen,
    OrderCancelled,
    OrderDelayed,
    OrderMakingStarted,
    OrderPaid,
    OrderPlaced,
    OrderRefunded,
    OrderShipped,
    WithdrawalReceived,
)
from modellbahn.modules.sales.domain.model import Order, OrderStatus
from modellbahn.modules.site.contracts.next_fair import NextFair
from modellbahn.platform.bank import BankAccount
from modellbahn.platform.clock import Clock
from modellbahn.platform.events import DomainEvent
from modellbahn.platform.mail import MailAttachment, MailContent, Mailer, compose
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
        shop_email: str = "",
        bank_account: BankAccount | None = None,
        invoices: InvoiceService | None = None,
    ) -> None:
        self._uow = uow_factory
        self._mailer = mailer
        self._clock = clock
        self._base_url = public_base_url
        self._shop_name = shop_name
        self._sender = tuple(sender)
        self._shop_email = shop_email
        self._bank = bank_account
        self._invoices = invoices

    def register(self, registry: HandlerRegistry) -> None:
        """Subscribe the handlers to their events."""
        registry.register(EmailVerified, self.adopt_guest_orders)
        registry.register(AccountDeleted, self.remove_address_book)
        registry.register(OrderPlaced, self.send_receipt)
        registry.register(OrderPaid, self.send_confirmation)
        registry.register(BankTransferChosen, self.send_transfer_details)
        registry.register(OrderShipped, self.send_shipped_notice)
        registry.register(OrderCancelled, self.send_cancellation_notice)
        registry.register(OrderRefunded, self.send_refund_notice)
        registry.register(WithdrawalReceived, self.confirm_withdrawal)
        registry.register(AllocationBackordered, self.learn_lead_time)
        registry.register(OrderDelayed, self.send_delay_notice)
        registry.register(PrintJobChanged, self.note_making_started)
        registry.register(OrderMakingStarted, self.send_making_notice)

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
                bank_transfer=self._bank is not None,
            )
            await self._send(event, order, content)

    async def send_transfer_details(self, event: BankTransferChosen) -> None:
        """The bank details for payment in advance, while the order waits for the money."""
        order = await self._order(event)
        if order is None or self._bank is None or order.awaited_transfer is None:
            # Paid or cancelled before the mail went out, or no account any more.
            return
        content = mails.bank_transfer_mail(order, bank=self._bank, base_url=self._base_url)
        await self._send(event, order, content)

    async def send_confirmation(self, event: OrderPaid) -> None:
        order = await self._order(event)
        if order is not None:
            content = mails.confirmation_mail(
                order, base_url=self._base_url, shop_name=self._shop_name
            )
            await self._send(event, order, content)

    async def learn_lead_time(self, event: AllocationBackordered) -> None:
        """A paid piece has to be made: if the order's checkout promised no lead time, the
        order takes the longest of the pieces waiting now (the parcel leaves complete)."""
        async with self._uow() as uow:
            order = await uow.orders.get(event.order_id, for_update=True)
            if order is None or order.lead_time_weeks is not None:
                return
            waiting = set((await uow.inventory.pick_progress(order.id)).waiting_variant_ids)
            waiting.add(event.variant_id)
            variants = await uow.catalog.sale_variants(waiting)
            made = [v.lead_time_weeks for v in variants.values() if v.lead_time_weeks]
            # A variant no longer made again still has to be made for this paid order.
            weeks = (
                (max(w[0] for w in made), max(w[1] for w in made))
                if made
                else await uow.catalog.shop_lead_time()
            )
            delayed = order.learn_lead_time(weeks, self._clock.now())
            if delayed is None:
                return
            uow.publish(delayed)
            await uow.commit()
        _logger.info(
            "sales.order.delayed",
            order=order.number,
            lead_time_weeks=list(weeks),
        )

    async def send_delay_notice(self, event: OrderDelayed) -> None:
        """Tell the customer which pieces are made for them, and when the parcel leaves."""
        order = await self._order(event)
        if order is None or order.status is not OrderStatus.PAID:
            # Cancelled or (rarely) shipped meanwhile: their own mail says what matters.
            return
        async with self._uow() as uow:
            waiting = set((await uow.inventory.pick_progress(order.id)).waiting_variant_ids)
        titles = [line.title for line in order.lines if line.variant_id in waiting]
        if not titles:
            # Made already by the time the mail goes out: the parcel is on its way soon.
            return
        content = mails.delay_mail(order, titles=titles, base_url=self._base_url)
        await self._send(event, order, content)

    async def note_making_started(self, event: PrintJobChanged) -> None:
        """A plate started printing: every paid order it makes parts for notes it once."""
        if event.change != "started":
            return
        async with self._uow() as uow:
            served = await uow.inventory.orders_served_by_plate(event.aggregate_id)
        for order_id in sorted(served):
            async with self._uow() as uow:
                order = await uow.orders.get(order_id, for_update=True)
                started = order.start_making(self._clock.now()) if order else None
                if started is None:
                    continue
                uow.publish(started)
                await uow.commit()
            _logger.info("sales.order.making_started", order=started.number, job=event.number)

    async def send_making_notice(self, event: OrderMakingStarted) -> None:
        """Tell the customer the workshop is making their pieces now."""
        order = await self._order(event)
        if order is None or order.status is not OrderStatus.PAID:
            return
        async with self._uow() as uow:
            waiting = set((await uow.inventory.pick_progress(order.id)).waiting_variant_ids)
        titles = [line.title for line in order.lines if line.variant_id in waiting]
        if not titles:
            return
        content = mails.making_mail(order, titles=titles, base_url=self._base_url)
        await self._send(event, order, content)

    async def send_shipped_notice(self, event: OrderShipped) -> None:
        """The parcel is on its way; the invoice comes along as a PDF (ADR 0038)."""
        order = await self._order(event)
        if order is not None:
            invoice = await self._invoices.invoice_for(order.id) if self._invoices else None
            content = mails.shipped_mail(
                order,
                base_url=self._base_url,
                next_fair=await self._next_fair(),
                invoice_number=invoice.number if invoice else None,
            )
            attachments = (MailAttachment(invoice.filename, invoice.document),) if invoice else ()
            await self._send(event, order, content, attachments=attachments)

    async def send_cancellation_notice(self, event: OrderCancelled) -> None:
        order = await self._order(event)
        if order is not None:
            content = mails.cancelled_mail(
                order,
                base_url=self._base_url,
                refunded=event.refunded,
                by_transfer=event.refund_by_transfer,
            )
            await self._send(event, order, content)
            if event.refunded and event.refund_by_transfer:
                await self._ask_to_transfer_back(order, event.refund_cents or order.total_cents)

    async def send_refund_notice(self, event: OrderRefunded) -> None:
        """Money went back; after the invoice, its correction comes along (ADR 0038)."""
        order = await self._order(event)
        if order is not None:
            correction = await self._invoices.correction_for(event) if self._invoices else None
            content = mails.refunded_mail(
                order,
                amount_cents=event.amount_cents,
                base_url=self._base_url,
                by_transfer=event.by_transfer,
                correction_number=correction.number if correction else None,
            )
            attachments = (
                (MailAttachment(correction.filename, correction.document),) if correction else ()
            )
            await self._send(event, order, content, attachments=attachments)
            if event.by_transfer:
                await self._ask_to_transfer_back(order, event.amount_cents)

    async def _ask_to_transfer_back(self, order: Order, amount_cents: int) -> None:
        """Money paid in advance goes back by hand: the shop gets a to-do by e-mail."""
        if not self._shop_email:
            _logger.warning("sales.transfer_back.no_shop_email", order=order.number)
            return
        await self._mailer.send(
            compose(
                mails.transfer_back_mail(order, amount_cents=amount_cents, base_url=self._base_url),
                to=self._shop_email,
                shop_name=self._shop_name,
                sender=self._sender,
            )
        )
        _logger.info("sales.transfer_back.requested", order=order.number)

    async def confirm_withdrawal(self, event: WithdrawalReceived) -> None:
        """Confirm the receipt to the consumer at once, and tell the shop."""
        async with self._uow() as uow:
            withdrawal = await uow.withdrawals.get(event.aggregate_id)
        if withdrawal is None:  # pragma: no cover - withdrawals are never deleted
            _logger.warning("sales.withdrawal.missing", event_id=str(event.event_id))
            return
        await self._mailer.send(
            compose(
                mails.withdrawal_receipt_mail(withdrawal),
                to=withdrawal.email,
                shop_name=self._shop_name,
                sender=self._sender,
            )
        )
        if self._shop_email:
            await self._mailer.send(
                compose(
                    mails.withdrawal_notice_mail(withdrawal, base_url=self._base_url),
                    to=self._shop_email,
                    shop_name=self._shop_name,
                    sender=self._sender,
                )
            )
        _logger.info(
            "sales.withdrawal.confirmed",
            event_id=str(event.event_id),
            withdrawal_id=str(withdrawal.id),
            shop_notified=bool(self._shop_email),
        )

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

    async def _send(
        self,
        event: DomainEvent,
        order: Order,
        content: MailContent,
        *,
        attachments: Sequence[MailAttachment] = (),
    ) -> None:
        await self._mailer.send(
            compose(
                content,
                to=order.email,
                shop_name=self._shop_name,
                sender=self._sender,
                attachments=attachments,
            )
        )
        _logger.info(
            "sales.mail.sent",
            event_id=str(event.event_id),
            event_type=event.event_type,
            order=order.number,
        )
