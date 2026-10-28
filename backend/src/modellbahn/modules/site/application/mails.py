"""The German e-mails of the fair news (content only; the layout is in ``platform.mail``)."""

from typing import Final

from modellbahn.modules.site.domain.dates import date_range
from modellbahn.modules.site.domain.model import CONFIRMATION_LIFETIME, Fair
from modellbahn.platform.mail import MailAction, MailContent, MailRow

FAIRS_PATH: Final = "/termine"
CONFIRM_PATH: Final = "/termine/bestaetigen"
UNSUBSCRIBE_PATH: Final = "/termine/abmelden"


def unsubscribe_link(base_url: str, token: str) -> str:
    return f"{base_url}{UNSUBSCRIBE_PATH}?token={token}"


def calendar_link(base_url: str, fair: Fair) -> str:
    return f"{base_url}/api/v1/store/fairs/{fair.id}/calendar.ics"


def confirmation_mail(*, base_url: str, token: str, shop_name: str) -> MailContent:
    """The double opt-in: nothing else is sent before this link was followed."""
    days = CONFIRMATION_LIFETIME.days
    return MailContent(
        subject=f"Bitte bestätige die Messe-Post von {shop_name}",
        greeting="Hallo,",
        paragraphs=(
            f"du möchtest erfahren, wann und wo {shop_name} auf Messen ausstellt. Bitte "
            "bestätige das mit dem Knopf; erst dann schicken wir dir Termine.",
        ),
        action=MailAction(
            label="Anmeldung bestätigen", url=f"{base_url}{CONFIRM_PATH}?token={token}"
        ),
        closing=(
            f"Der Link gilt {days} Tage. Hast du dich nicht angemeldet? Dann ignoriere diese "
            f"E-Mail einfach: Ohne Bestätigung löschen wir deine Adresse nach {days} Tagen.",
        ),
    )


def announcement_mail(
    fair: Fair, *, base_url: str, unsubscribe_token: str, shop_name: str
) -> MailContent:
    """One fair, to every confirmed subscriber, with the way out in every mail."""
    when = date_range(fair.starts_on, fair.ends_on)
    rows = [MailRow("Wann", when), MailRow("Wo", fair.place())]
    if fair.booth:
        rows.append(MailRow("Stand", fair.booth))
    if fair.hours:
        rows.append(MailRow("Geöffnet", "; ".join(fair.hours.splitlines())))
    paragraphs = [
        f"bald kannst du unsere Modelle wieder in die Hand nehmen: {shop_name} stellt auf "
        f"der Messe „{fair.name}“ aus.",
    ]
    if fair.note:
        paragraphs.append(fair.note)
    return MailContent(
        subject=f"Wir stellen aus: {fair.name}, {when}",
        greeting="Hallo,",
        paragraphs=paragraphs,
        rows=rows,
        action=MailAction(label="Alle Messetermine", url=f"{base_url}{FAIRS_PATH}"),
        closing=(
            f"In den Kalender übernehmen: {calendar_link(base_url, fair)}",
            "Komm vorbei, wir freuen uns auf dich!",
            "Keine Messe-Post mehr? Hier abmelden: "
            f"{unsubscribe_link(base_url, unsubscribe_token)}",
        ),
    )
