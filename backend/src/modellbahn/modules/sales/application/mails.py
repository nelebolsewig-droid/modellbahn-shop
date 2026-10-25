"""The German e-mails of the sales module (content only; the layout is in ``platform.mail``)."""

from typing import Final

from modellbahn.modules.sales.domain.model import CancelReason, Order
from modellbahn.platform.mail import MailAction, MailContent, MailRow

ORDER_STATUS_PATH: Final = "/bestellung"


def format_euro(cents: int) -> str:
    """German notation, e.g. ``1.234,50 €`` (with a no-break space before the sign)."""
    euros, rest = divmod(cents, 100)
    return f"{euros:,}".replace(",", ".") + f",{rest:02d}\u00a0€"


def status_link(base_url: str, order: Order) -> str:
    return f"{base_url}{ORDER_STATUS_PATH}/{order.public_token}"


def _rows(order: Order) -> list[MailRow]:
    rows = [
        # The typographic multiplication sign, as on an invoice.
        MailRow(f"{line.quantity} × {line.title}", format_euro(line.line_total_cents))  # noqa: RUF001
        for line in order.lines
    ]
    shipping = format_euro(order.shipping_cents) if order.shipping_cents else "kostenlos"
    rows.append(MailRow("Versand", shipping))
    rows.append(MailRow("Summe", format_euro(order.total_cents), strong=True))
    rows.append(MailRow("darin enthalten 19 % MwSt.", format_euro(order.tax_cents)))
    return rows


def _greeting(order: Order) -> str:
    return f"Hallo {order.shipping_address.recipient},"


def confirmation_mail(order: Order, *, base_url: str, shop_name: str) -> MailContent:
    address = ", ".join(order.shipping_address.lines())
    return MailContent(
        subject=f"Deine Bestellung {order.number}",
        greeting=_greeting(order),
        paragraphs=(
            f"vielen Dank für deine Bestellung bei {shop_name}! Deine Zahlung ist eingegangen, "
            "die Bestellung ist damit verbindlich.",
            f"Bestellnummer {order.number}:",
        ),
        rows=_rows(order),
        action=MailAction(label="Bestellung ansehen", url=status_link(base_url, order)),
        closing=(
            f"Wir schicken alles an: {address}. Sobald das Paket unterwegs ist, "
            "bekommst du eine weitere E-Mail.",
        ),
    )


def shipped_mail(order: Order, *, base_url: str) -> MailContent:
    parcel = "Dein Paket ist unterwegs."
    if order.tracking_number:
        carrier = f" bei {order.carrier}" if order.carrier else ""
        parcel = (
            f"Dein Paket ist unterwegs, die Sendungsnummer{carrier} ist {order.tracking_number}."
        )
    return MailContent(
        subject=f"Deine Bestellung {order.number} ist unterwegs",
        greeting=_greeting(order),
        paragraphs=(f"wir haben deine Bestellung {order.number} heute verschickt. {parcel}",),
        action=MailAction(label="Bestellung ansehen", url=status_link(base_url, order)),
        closing=("Viel Freude beim Bauen!",),
    )


def cancelled_mail(order: Order, *, base_url: str, refunded: bool) -> MailContent:
    if order.cancel_reason is CancelReason.PAYMENT_TIMEOUT:
        why = (
            f"deine Bestellung {order.number} haben wir storniert, weil die Zahlung nicht "
            "innerhalb von 24 Stunden eingegangen ist."
        )
    else:
        why = f"deine Bestellung {order.number} haben wir storniert."
    paragraphs = [why]
    if order.cancel_note:
        paragraphs.append(f"Hinweis: {order.cancel_note}")
    if refunded:
        paragraphs.append(
            f"Den bezahlten Betrag von {format_euro(order.total_cents)} erstatten wir dir "
            "auf dem Weg, auf dem du bezahlt hast."
        )
    return MailContent(
        subject=f"Deine Bestellung {order.number} wurde storniert",
        greeting=_greeting(order),
        paragraphs=tuple(paragraphs),
        action=MailAction(label="Bestellung ansehen", url=status_link(base_url, order)),
        closing=("Bei Fragen antworte nicht auf diese E-Mail, sondern schreib uns über den Shop.",),
    )
