"""The German e-mails of the sales module (content only; the layout is in ``platform.mail``)."""

from datetime import datetime
from typing import Final
from zoneinfo import ZoneInfo

from modellbahn.modules.sales.domain.model import CancelReason, Order
from modellbahn.modules.sales.domain.withdrawals import Withdrawal
from modellbahn.modules.site.contracts.next_fair import NextFair
from modellbahn.platform.mail import MailAction, MailContent, MailRow

ORDER_STATUS_PATH: Final = "/bestellung"
FAIRS_PATH: Final = "/termine"
ADMIN_ORDERS_PATH: Final = "/admin/bestellungen"
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
    elif order.cancel_reason is CancelReason.WITHDRAWN:
        why = (
            f"du hast deine Bestellung {order.number} widerrufen, bevor wir sie verschickt "
            "haben. Wir haben sie deshalb storniert."
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


def _received(withdrawal: Withdrawal) -> str:
    """``04.11.2026 um 15:42 Uhr``: when the declaration came in, in the shop's time zone."""
    local = withdrawal.received_at.astimezone(SHOP_TIME_ZONE)
    return f"{local:%d.%m.%Y} um {local:%H:%M} Uhr"


def _declared(withdrawal: Withdrawal) -> tuple[list[MailRow], str]:
    """What the consumer declared, as the confirmation repeats it (§ 356a Abs. 4 BGB)."""
    rows = [
        MailRow("Name", withdrawal.name),
        MailRow("Bestellnummer", withdrawal.order_reference),
        MailRow("E-Mail-Adresse", withdrawal.email),
        MailRow("Eingegangen am", _received(withdrawal), strong=True),
    ]
    scope = (
        "Widerrufen: die ganze Bestellung."
        if withdrawal.whole_order
        else f"Widerrufen: {withdrawal.scope}"
    )
    return rows, scope


def withdrawal_receipt_mail(withdrawal: Withdrawal) -> MailContent:
    """The confirmation of receipt on a durable medium: what came in, and when.

    It repeats only what the consumer entered, so it tells nobody whether an order with
    that number exists.
    """
    rows, scope = _declared(withdrawal)
    return MailContent(
        subject=f"Eingangsbestätigung: dein Widerruf zu Bestellung {withdrawal.order_reference}",
        greeting=f"Hallo {withdrawal.name},",
        paragraphs=(
            f"dein Widerruf ist am {_received(withdrawal)} bei uns eingegangen. Diese E-Mail "
            "bestätigt den Eingang. Das hast du uns übermittelt:",
            scope,
        ),
        rows=rows,
        closing=(
            "Ist die Ware schon bei dir, schick sie bitte innerhalb von 14 Tagen an die "
            "Anschrift am Ende dieser E-Mail. Die Kosten der Rücksendung trägst du.",
            "Den Kaufpreis und die Versandkosten erstatten wir dir spätestens 14 Tage nach "
            "Eingang deines Widerrufs, auf dem Weg, auf dem du bezahlt hast. Wir dürfen damit "
            "warten, bis die Ware wieder bei uns ist oder du die Rücksendung nachweist. Ist die "
            "Bestellung noch nicht verschickt, stornieren wir sie.",
            "Bewahre diese E-Mail auf: Sie belegt, wann dein Widerruf eingegangen ist.",
        ),
    )


def withdrawal_notice_mail(withdrawal: Withdrawal, *, base_url: str) -> MailContent:
    """The shop's notice: a withdrawal came in, and whether it names one of its orders."""
    rows, scope = _declared(withdrawal)
    if withdrawal.order_id is not None:
        match = "Nummer und E-Mail-Adresse passen zu einer Bestellung des Shops."
        link = f"{base_url}{ADMIN_ORDERS_PATH}/{withdrawal.order_id}"
    else:
        match = (
            "Zu Nummer und E-Mail-Adresse passt keine Bestellung des Shops. Bitte von Hand "
            "prüfen, etwa ob es um einen Kauf auf eBay geht."
        )
        link = f"{base_url}{ADMIN_ORDERS_PATH}"
    return MailContent(
        subject=f"Widerruf eingegangen: {withdrawal.order_reference}",
        greeting="Hallo,",
        paragraphs=(
            "über die Widerrufsfunktion des Shops ist ein Widerruf eingegangen:",
            scope,
        ),
        rows=rows,
        action=MailAction(label="Im Stellwerk ansehen", url=link),
        closing=(match, "Die Eingangsbestätigung ist an die angegebene E-Mail-Adresse gegangen."),
    )


def refunded_mail(order: Order, *, amount_cents: int, base_url: str) -> MailContent:
    """Money went back after a return (ADR 0020)."""
    whole = order.refunded_cents >= order.total_cents
    return MailContent(
        subject=f"Erstattung für deine Bestellung {order.number}",
        greeting=_greeting(order),
        paragraphs=(
            f"wir haben dir {format_euro(amount_cents)} für deine Bestellung {order.number} "
            "erstattet, auf dem Weg, auf dem du bezahlt hast. Bis das Geld auf deinem Konto "
            "ist, kann es je nach Bank ein paar Tage dauern.",
            *(() if whole else (f"Insgesamt erstattet: {format_euro(order.refunded_cents)}.",)),
        ),
        action=MailAction(label="Bestellung ansehen", url=status_link(base_url, order)),
        closing=("Danke, dass du die Ware zurückgeschickt hast.",),
    )


def refund_reminder_mail(
    due: list[tuple[Withdrawal, datetime]], *, now: datetime, base_url: str
) -> MailContent:
    """The shop's reminder: refunds after a withdrawal that fall due (§ 357 Abs. 1 BGB)."""
    rows = [
        MailRow(
            f"{withdrawal.order_reference} · {withdrawal.name}",
            ("überfällig seit " if deadline < now else "fällig bis ")
            + f"{deadline.astimezone(SHOP_TIME_ZONE):%d.%m.%Y}",
            strong=deadline < now,
        )
        for withdrawal, deadline in due
    ]
    count = "Eine Erstattung" if len(due) == 1 else f"{len(due)} Erstattungen"
    return MailContent(
        subject=f"Erinnerung: {count} nach Widerruf fällig",
        greeting="Hallo,",
        paragraphs=(
            f"{count} nach einem Widerruf {'steht' if len(due) == 1 else 'stehen'} noch aus. "
            "Spätestens 14 Tage nach Eingang des Widerrufs muss das Geld zurück; warten darf "
            "man, bis die Ware wieder da ist oder der Kunde die Rücksendung nachweist.",
        ),
        rows=rows,
        action=MailAction(label="Im Stellwerk erstatten", url=f"{base_url}{ADMIN_ORDERS_PATH}"),
        closing=(
            # The button's own label, with its typographic dash.
            "Ist die Ware da: Bestellung öffnen, „Rücksendung erhalten – erstatten“. SumUp "  # noqa: RUF001
            "zahlt zurück, der Kunde bekommt eine E-Mail. Diese Erinnerung kommt täglich, "
            "bis alles erstattet ist.",
        ),
    )
