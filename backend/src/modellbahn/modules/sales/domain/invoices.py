"""Invoices and their corrections for shipped orders (ADR 0038).

An order gets its invoice when it ships: the date of delivery belongs on an invoice
(§ 14 Abs. 4 Nr. 6 UStG), and only the dispatch fixes it. Money given back afterwards gets
an invoice correction of its own that names the invoice it corrects. Both are numbered in
their own unbroken series per year (``RE-2026-00001``, ``RK-2026-00001``) and are never
changed once issued: what the customer received is what the shop keeps.

This module decides what goes on the document; drawing it is the renderer's job.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from typing import Final
from uuid import UUID
from zoneinfo import ZoneInfo

from modellbahn.modules.sales.domain.errors import InvalidOrderStateError
from modellbahn.modules.sales.domain.model import (
    VAT_PERCENT,
    Order,
    OrderStatus,
    SalesChannel,
    included_vat,
)
from modellbahn.platform.ids import new_id

SHOP_TIME_ZONE: Final = ZoneInfo("Europe/Berlin")
"""Dates on the documents are the shop's own calendar days."""


class InvoiceKind(StrEnum):
    INVOICE = "invoice"
    CORRECTION = "correction"
    """Money given back after the invoice: an invoice correction (Rechnungskorrektur)."""


PREFIXES: Final = {InvoiceKind.INVOICE: "RE", InvoiceKind.CORRECTION: "RK"}

TITLES: Final = {InvoiceKind.INVOICE: "Rechnung", InvoiceKind.CORRECTION: "Rechnungskorrektur"}


def invoice_number(kind: InvoiceKind, year: int, serial: int) -> str:
    """``RE-2026-00001`` for invoices, ``RK-2026-00001`` for corrections."""
    if serial < 1:
        msg = "serials start at 1"
        raise ValueError(msg)
    return f"{PREFIXES[kind]}-{year}-{serial:05d}"


def local_date(moment: datetime) -> date:
    return moment.astimezone(SHOP_TIME_ZONE).date()


@dataclass(frozen=True, slots=True)
class Issuer:
    """Who issues the invoices: the shop's operator, as § 14 Abs. 4 UStG asks for it.

    ``tax_label`` is ``USt-IdNr.`` or ``Steuernummer``: the VAT ID where there is one,
    otherwise the tax number from the tax office.
    """

    name: str
    owner: str
    street: str
    postal_code: str
    city: str
    country: str
    email: str
    phone: str
    tax_label: str
    tax_id: str

    def address_lines(self) -> tuple[str, ...]:
        country = "" if self.country in {"", "Deutschland"} else self.country
        lines = (self.name, self.owner, self.street, f"{self.postal_code} {self.city}", country)
        return tuple(line for line in lines if line)

    def sender_line(self) -> str:
        """The small line above the recipient in the window of the envelope."""
        return " · ".join(
            part
            for part in (self.name, self.street, f"{self.postal_code} {self.city}")
            if part.strip()
        )


@dataclass(frozen=True, slots=True)
class InvoiceLine:
    description: str
    quantity: int
    unit_cents: int
    total_cents: int
    detail: str = ""


@dataclass(frozen=True, slots=True)
class InvoiceDocument:
    """Everything printed on one invoice or correction; amounts are gross, in cents.

    A correction carries negative amounts: it takes back part of the invoice.
    """

    kind: InvoiceKind
    number: str
    issued_on: date
    delivered_on: date
    order_number: str
    issuer: Issuer
    recipient: tuple[str, ...]
    email: str
    lines: tuple[InvoiceLine, ...]
    total_cents: int
    tax_cents: int
    vat_percent: int
    notes: tuple[str, ...]
    corrects: tuple[str, date] | None = None
    """For a correction: the number and date of the invoice it corrects."""

    @property
    def title(self) -> str:
        return TITLES[self.kind]

    @property
    def net_cents(self) -> int:
        return self.total_cents - self.tax_cents


def _recipient(order: Order) -> tuple[str, ...]:
    """The address as on the parcel; the country only abroad."""
    lines = order.shipping_address.lines()
    return tuple(lines[:-1] if order.shipping_address.country_code == "DE" else lines)


def _payment_note(order: Order) -> str:
    payment = order.captured_payment or next(iter(order.payments), None)
    paid = f" am {local_date(order.paid_at):%d.%m.%Y}" if order.paid_at else ""
    if order.channel is SalesChannel.EBAY:
        return f"Bezahlt über eBay{paid}."
    if payment is not None and payment.by_transfer:
        return f"Bezahlt per Überweisung{paid}."
    return f"Bezahlt per Karte (SumUp){paid}."


def _check_shipped(order: Order) -> datetime:
    if order.status is not OrderStatus.SHIPPED or order.shipped_at is None:
        msg = f"an order that is {order.status} gets no invoice yet"
        raise InvalidOrderStateError(msg)
    return order.shipped_at


def invoice_document(
    order: Order, *, number: str, issuer: Issuer, issued_at: datetime
) -> InvoiceDocument:
    """The invoice of a shipped order: its lines, the shipping, VAT included at 19 %."""
    shipped_at = _check_shipped(order)
    lines = [
        InvoiceLine(
            description=line.title,
            detail=f"Art.-Nr. {line.sku}",
            quantity=line.quantity,
            unit_cents=line.unit_price_cents,
            total_cents=line.line_total_cents,
        )
        for line in order.lines
    ]
    if order.shipping_cents:
        lines.append(
            InvoiceLine(
                description="Versand",
                detail=order.carrier or "",
                quantity=1,
                unit_cents=order.shipping_cents,
                total_cents=order.shipping_cents,
            )
        )
    return InvoiceDocument(
        kind=InvoiceKind.INVOICE,
        number=number,
        issued_on=local_date(issued_at),
        delivered_on=local_date(shipped_at),
        order_number=order.number,
        issuer=issuer,
        recipient=_recipient(order),
        email=order.email,
        lines=tuple(lines),
        total_cents=order.total_cents,
        tax_cents=order.tax_cents,
        vat_percent=VAT_PERCENT,
        notes=(_payment_note(order), "Vielen Dank für deine Bestellung!"),
    )


def correction_document(
    order: Order,
    *,
    invoice: "Invoice",
    number: str,
    amount_cents: int,
    issuer: Issuer,
    issued_at: datetime,
) -> InvoiceDocument:
    """The correction for money given back after the invoice, e.g. after a withdrawal.

    It takes back ``amount_cents`` gross with the VAT contained in it; the whole order if
    everything went back, else one line for the part.
    """
    if amount_cents <= 0:
        msg = "a correction takes back a positive amount"
        raise ValueError(msg)
    shipped_at = _check_shipped(order)
    whole = amount_cents == order.total_cents
    if whole:
        lines = tuple(
            InvoiceLine(
                description=line.description,
                detail=line.detail,
                quantity=line.quantity,
                unit_cents=-line.unit_cents,
                total_cents=-line.total_cents,
            )
            for line in invoice_document(
                order, number=invoice.number, issuer=issuer, issued_at=invoice.issued_at
            ).lines
        )
        tax = -order.tax_cents
    else:
        lines = (
            InvoiceLine(
                description="Erstattung",
                detail=f"zu Bestellung {order.number}",
                quantity=1,
                unit_cents=-amount_cents,
                total_cents=-amount_cents,
            ),
        )
        tax = -included_vat(amount_cents)
    return InvoiceDocument(
        kind=InvoiceKind.CORRECTION,
        number=number,
        issued_on=local_date(issued_at),
        delivered_on=local_date(shipped_at),
        order_number=order.number,
        issuer=issuer,
        recipient=_recipient(order),
        email=order.email,
        lines=lines,
        total_cents=-amount_cents,
        tax_cents=tax,
        vat_percent=VAT_PERCENT,
        notes=(
            f"Wir haben dir {_euro(amount_cents)} erstattet.",
            "Der Betrag geht auf dem Weg zurück, auf dem du bezahlt hast.",
        ),
        corrects=(invoice.number, local_date(invoice.issued_at)),
    )


def _euro(cents: int) -> str:
    euros, rest = divmod(cents, 100)
    return f"{euros:,}".replace(",", ".") + f",{rest:02d}\u00a0€"


@dataclass(eq=False)
class Invoice:
    """An issued invoice or correction with its PDF, as the customer received it.

    ``source`` makes issuing idempotent: ``order`` for the order's invoice, the refund
    event's id for a correction. Delivery from the outbox is at least once.
    """

    id: UUID
    order_id: UUID
    kind: InvoiceKind
    number: str
    source: str
    total_cents: int
    tax_cents: int
    document: bytes
    issued_at: datetime
    corrects_id: UUID | None = None

    @classmethod
    def issue(
        cls,
        *,
        order_id: UUID,
        content: InvoiceDocument,
        source: str,
        document: bytes,
        issued_at: datetime,
        corrects_id: UUID | None = None,
    ) -> "Invoice":
        if not document:
            msg = "an invoice needs its document"
            raise ValueError(msg)
        if (content.kind is InvoiceKind.CORRECTION) != (corrects_id is not None):
            msg = "a correction, and only a correction, names the invoice it corrects"
            raise ValueError(msg)
        return cls(
            id=new_id(),
            order_id=order_id,
            kind=content.kind,
            number=content.number,
            source=source,
            total_cents=content.total_cents,
            tax_cents=content.tax_cents,
            document=document,
            issued_at=issued_at,
            corrects_id=corrects_id,
        )

    @property
    def filename(self) -> str:
        """``Rechnung-RE-2026-00001.pdf``, as the attachment and the download are named."""
        return f"{TITLES[self.kind]}-{self.number}.pdf"


ORDER_SOURCE: Final = "order"
"""The ``source`` of an order's invoice: there is one per order."""


def latest_invoice(invoices: Sequence[Invoice]) -> Invoice | None:
    """The order's invoice proper (not a correction), if issued."""
    return next((i for i in invoices if i.kind is InvoiceKind.INVOICE), None)
