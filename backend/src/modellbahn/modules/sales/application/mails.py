"""The German e-mails of the sales module (content only; the layout is in ``platform.mail``)."""

from datetime import datetime
from typing import Final
from zoneinfo import ZoneInfo

from modellbahn.modules.sales.domain.model import CancelReason, Order
from modellbahn.modules.site.contracts.next_fair import NextFair
from modellbahn.platform.mail import MailAction, MailContent, MailRow

ORDER_STATUS_PATH: Final = "/bestellung"
FAIRS_PATH: Final = "/termine"
SHOP_TIME_ZONE: Final = ZoneInfo("Europe/Berlin")


def format_euro(cents: int) -> str:
    """German notation, e.g. ``1.234,50 €`` (with a no-break space before the sign)."""
    euros, rest = divmod(cents, 100)
    return f"{euros:,}".replace(",", ".") + f",{rest:02d}\u00a0€"


def _local_time(moment: datetime) -> str:
    """``26.10.2026, 10:00 Uhr`` in the shop's time zone."""
    local = moment.astimezone(SHOP_TIME_ZONE)
    return f"{local:%d.%m.%Y, %H:%M} Uhr"


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


def fair_hint(fair: NextFair | None, *, base_url: str) -> tuple[str, ...]:
    """Where to meet the workshop next, as a closing line; nothing when no fair is planned."""
    if fair is None:
        return ()
    place = f"{fair.venue}, {fair.city}" if fair.venue else fair.city
    booth = f", {fair.booth}" if fair.booth else ""
    return (
        f"Lust, unsere Modelle in die Hand zu nehmen? Als Nächstes stellen wir auf der Messe "
        f"„{fair.name}“ aus: {fair.when}, {place}{booth}. Alle Termine: {base_url}{FAIRS_PATH}",
    )


def received_mail(
    order: Order, *, base_url: str, shop_name: str, next_fair: NextFair | None = None
) -> MailContent:
    """The confirmation of receipt (§ 312i BGB), with the way to pay."""
    due = order.payment_due_at
    deadline = (
        f" Bitte bezahle bis {_local_time(due)}; danach stornieren wir sie automatisch."
        if due is not None
        else ""
    )
    return MailContent(
        subject=f"Bestellung {order.number} eingegangen",
        greeting=_greeting(order),
        paragraphs=(
            f"danke für deine Bestellung bei {shop_name}! Wir haben sie erhalten; verbindlich "
            f"wird sie, sobald die Zahlung eingegangen ist.{deadline}",
            f"Bestellnummer {order.number}:",
        ),
        rows=_rows(order),
        # Sent a little later than the order was placed, it may already be paid by then.
        action=(
            MailAction(label="Jetzt bezahlen", url=f"{status_link(base_url, order)}/bezahlen")
            if due is not None
            else MailAction(label="Bestellung ansehen", url=status_link(base_url, order))
        ),
        closing=(
            "Hast du schon bezahlt, während diese E-Mail unterwegs war? Dann ist alles gut: "
            "Die Bestätigung der Zahlung kommt in einer eigenen E-Mail.",
            *fair_hint(next_fair, base_url=base_url),
        ),
    )


def confirmation_mail(order: Order, *, base_url: str, shop_name: str) -> MailContent:
    address = ", ".join(order.shipping_address.lines())
    return MailContent(
        subject=f"Zahlung eingegangen: Bestellung {order.number}",
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


def shipped_mail(order: Order, *, base_url: str, next_fair: NextFair | None = None) -> MailContent:
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
        closing=("Viel Freude beim Bauen!", *fair_hint(next_fair, base_url=base_url)),
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
