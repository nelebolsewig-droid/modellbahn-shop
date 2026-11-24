"""The delivery note that goes into the parcel (ADR 0047).

A packing slip without prices: who sent it, to whom, which pieces in which number, and a
box per line to tick while packing. Unlike the invoice it is no tax document, so it needs
no tax number and is written for any paid or shipped order, as often as asked; nothing is
stored, the order is the record.

This module decides what goes on the note; drawing it is the renderer's job.
"""

from dataclasses import dataclass
from datetime import date, datetime

from modellbahn.modules.sales.domain.errors import InvalidOrderStateError
from modellbahn.modules.sales.domain.invoices import local_date
from modellbahn.modules.sales.domain.model import Order, OrderStatus, SalesChannel
from modellbahn.platform.imprint import Imprint


@dataclass(frozen=True, slots=True)
class Sender:
    """The shop as it signs the note; parts the imprint lacks stay empty."""

    name: str
    street: str = ""
    postal_code: str = ""
    city: str = ""
    email: str = ""
    phone: str = ""
    website: str = ""

    @classmethod
    def of(cls, imprint: Imprint, *, website: str = "") -> "Sender":
        return cls(
            name=imprint.company or imprint.shop_name,
            street=imprint.street,
            postal_code=imprint.postal_code,
            city=imprint.city,
            email=imprint.email,
            phone=imprint.phone,
            website=website.split("://", 1)[-1].rstrip("/"),
        )

    @property
    def place(self) -> str:
        return f"{self.postal_code} {self.city}".strip()

    def sender_line(self) -> str:
        """The small line above the recipient in the window of the envelope."""
        return " · ".join(part for part in (self.name, self.street, self.place) if part)


@dataclass(frozen=True, slots=True)
class DeliveryLine:
    title: str
    sku: str
    quantity: int


@dataclass(frozen=True, slots=True)
class DeliveryNote:
    order_number: str
    ordered_on: date
    delivered_on: date
    sender: Sender
    recipient: tuple[str, ...]
    lines: tuple[DeliveryLine, ...]
    carrier: str = ""
    tracking_number: str = ""
    marketplace_ref: str = ""
    """The marketplace's own order number, e.g. eBay's, for the buyer to recognise."""

    @property
    def pieces(self) -> int:
        return sum(line.quantity for line in self.lines)

    @property
    def filename(self) -> str:
        return f"Lieferschein-{self.order_number}.pdf"


def delivery_note(order: Order, *, sender: Sender, printed_at: datetime) -> DeliveryNote:
    """The note of a paid or shipped order; dated the dispatch, or today before it."""
    if order.status not in {OrderStatus.PAID, OrderStatus.SHIPPED}:
        msg = f"an order that is {order.status} is not packed"
        raise InvalidOrderStateError(msg)
    address = order.shipping_address
    lines = address.lines()
    recipient = tuple(lines[:-1] if address.country_code == "DE" else lines)
    return DeliveryNote(
        order_number=order.number,
        ordered_on=local_date(order.placed_at),
        delivered_on=local_date(order.shipped_at or printed_at),
        sender=sender,
        recipient=recipient,
        lines=tuple(
            DeliveryLine(title=line.title, sku=line.sku, quantity=line.quantity)
            for line in sorted(order.lines, key=lambda line: line.position)
        ),
        carrier=order.carrier,
        tracking_number=order.tracking_number,
        marketplace_ref=(order.external_ref or "")
        if order.channel is not SalesChannel.SHOP
        else "",
    )
