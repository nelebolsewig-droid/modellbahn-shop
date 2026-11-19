"""Invoices and corrections (ADR 0038): issued by the worker, read by Stellwerk and customer.

* **Invoice:** when an order ships, it gets its invoice with the next number of the year.
  The shipping e-mail carries it as a PDF.
* **Correction:** money given back for a shipped order (after a return or withdrawal) gets
  a correction that names the invoice. The refund e-mail carries it.

Issuing is idempotent per occasion (the order, or the refund event), so the outbox may
deliver an event twice and the mail handler may ask for the document the issuing handler
created already. Without an :class:`Issuer` (no tax number configured yet) nothing is
issued, and the Stellwerk says so.
"""

from datetime import datetime
from uuid import UUID

import structlog

from modellbahn.modules.sales.application.common import UnitOfWorkFactory
from modellbahn.modules.sales.application.ports import InvoiceRenderer, SalesUnitOfWork
from modellbahn.modules.sales.domain.errors import InvoiceNotFoundError, OrderNotFoundError
from modellbahn.modules.sales.domain.events import OrderRefunded, OrderShipped
from modellbahn.modules.sales.domain.invoices import (
    ORDER_SOURCE,
    Invoice,
    InvoiceKind,
    Issuer,
    correction_document,
    invoice_document,
    invoice_number,
    latest_invoice,
    local_date,
)
from modellbahn.modules.sales.domain.model import Order, OrderStatus
from modellbahn.platform.clock import Clock
from modellbahn.platform.outbox import HandlerRegistry

_logger = structlog.get_logger(__name__)


class InvoiceService:
    def __init__(
        self,
        *,
        uow_factory: UnitOfWorkFactory,
        clock: Clock,
        renderer: InvoiceRenderer,
        issuer: Issuer | None,
    ) -> None:
        self._uow = uow_factory
        self._clock = clock
        self._renderer = renderer
        self._issuer = issuer

    @property
    def issues_invoices(self) -> bool:
        """The operator and a tax number are configured: invoices are written."""
        return self._issuer is not None

    async def invoice_for(self, order_id: UUID) -> Invoice | None:
        """The shipped order's invoice, issued now if it has none yet.

        None if the order is not shipped, or no invoices are written.
        """
        if self._issuer is None:
            return None
        async with self._uow() as uow:
            existing = await uow.invoices.by_source(order_id, ORDER_SOURCE)
            if existing is not None:
                return existing
            order = await _locked(uow, order_id)
            if order.status is not OrderStatus.SHIPPED:
                return None
            # Locked now: a second worker waits here and then finds the first one's invoice.
            existing = await uow.invoices.by_source(order_id, ORDER_SOURCE)
            if existing is not None:
                return existing
            now = self._clock.now()
            number = await self._number(uow, InvoiceKind.INVOICE, now)
            content = invoice_document(order, number=number, issuer=self._issuer, issued_at=now)
            invoice = Invoice.issue(
                order_id=order.id,
                content=content,
                source=ORDER_SOURCE,
                document=self._renderer.render(content),
                issued_at=now,
            )
            uow.invoices.add(invoice)
            await uow.commit()
        _logger.info("sales.invoice.issued", order=order.number, invoice=invoice.number)
        return invoice

    async def correction_for(self, event: OrderRefunded) -> Invoice | None:
        """The correction for a refund after the invoice, issued now if not yet.

        None for a refund before the invoice (nothing to correct) or without invoices.
        """
        if self._issuer is None:
            return None
        source = str(event.event_id)
        async with self._uow() as uow:
            existing = await uow.invoices.by_source(event.aggregate_id, source)
            if existing is not None:
                return existing
            order = await _locked(uow, event.aggregate_id)
            existing = await uow.invoices.by_source(order.id, source)
            if existing is not None:
                return existing
            invoice = latest_invoice(await uow.invoices.for_order(order.id))
            if invoice is None:
                return None
            now = self._clock.now()
            number = await self._number(uow, InvoiceKind.CORRECTION, now)
            content = correction_document(
                order,
                invoice=invoice,
                number=number,
                amount_cents=event.amount_cents,
                issuer=self._issuer,
                issued_at=now,
            )
            correction = Invoice.issue(
                order_id=order.id,
                content=content,
                source=source,
                document=self._renderer.render(content),
                issued_at=now,
                corrects_id=invoice.id,
            )
            uow.invoices.add(correction)
            await uow.commit()
        _logger.info(
            "sales.invoice.corrected",
            order=order.number,
            invoice=invoice.number,
            correction=correction.number,
        )
        return correction

    async def for_order(self, order_id: UUID) -> list[Invoice]:
        async with self._uow() as uow:
            return await uow.invoices.for_order(order_id)

    async def get(self, invoice_id: UUID, *, order_id: UUID | None = None) -> Invoice:
        """An invoice by id; with ``order_id`` only if it belongs to that order."""
        async with self._uow() as uow:
            invoice = await uow.invoices.get(invoice_id)
        if invoice is None or (order_id is not None and invoice.order_id != order_id):
            raise InvoiceNotFoundError
        return invoice

    async def issue_on_shipment(self, event: OrderShipped) -> None:
        await self.invoice_for(event.aggregate_id)

    async def correct_on_refund(self, event: OrderRefunded) -> None:
        await self.correction_for(event)

    def register(self, registry: HandlerRegistry) -> None:
        """Issue for every order, marketplace orders included (their buyer gets no mail)."""
        registry.register(OrderShipped, self.issue_on_shipment)
        registry.register(OrderRefunded, self.correct_on_refund)

    async def _number(self, uow: SalesUnitOfWork, kind: InvoiceKind, now: datetime) -> str:
        year = local_date(now).year
        return invoice_number(kind, year, await uow.invoices.next_serial(kind, year))


async def _locked(uow: SalesUnitOfWork, order_id: UUID) -> Order:
    order = await uow.orders.get(order_id, for_update=True)
    if order is None:
        raise OrderNotFoundError
    return order
