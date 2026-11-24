"""The German e-mails of the newsletter (content only; the layout is in ``platform.mail``)."""

from collections.abc import Sequence
from typing import Final

from modellbahn.modules.newsletter.domain.model import CONFIRMATION_LIFETIME
from modellbahn.platform.mail import MailAction, MailCard, MailContent, MailSection

CONFIRM_PATH: Final = "/newsletter/bestaetigen"
UNSUBSCRIBE_PATH: Final = "/newsletter/abmelden"
ONE_CLICK_PATH: Final = "/api/v1/webhooks/newsletter/unsubscribe"
CATALOG_PATH: Final = "/katalog"
ACCOUNT_PATH: Final = "/konto"


def unsubscribe_link(base_url: str, token: str) -> str:
    return f"{base_url}{UNSUBSCRIBE_PATH}?token={token}"


def one_click_link(base_url: str, token: str) -> str:
    """For the mail program's own button (RFC 8058): it posts to this address."""
    return f"{base_url}{ONE_CLICK_PATH}?token={token}"


def confirmation_mail(
    *, base_url: str, token: str, shop_name: str, display_name: str
) -> MailContent:
    """The double opt-in: no issue goes out before this link was followed."""
    days = CONFIRMATION_LIFETIME.days
    return MailContent(
        subject=f"Bitte bestätige den Newsletter von {shop_name}",
        greeting=f"Hallo {display_name},",
        paragraphs=(
            f"du möchtest den Newsletter von {shop_name} bekommen: ein- bis zweimal im Monat "
            "die neuen Modelle und was zu deiner Sammlung passt. Bitte bestätige das mit dem "
            "Knopf; erst dann schicken wir dir den Newsletter.",
        ),
        action=MailAction(
            label="Newsletter bestätigen", url=f"{base_url}{CONFIRM_PATH}?token={token}"
        ),
        closing=(
            f"Der Link gilt {days} Tage. Abmelden kannst du dich jederzeit mit einem Klick, in "
            "jeder Ausgabe und in deinem Kundenkonto.",
            "Hast du das nicht angefordert? Dann ignoriere diese E-Mail einfach.",
        ),
    )


def issue_mail(
    *,
    number: int,
    display_name: str,
    new_cards: Sequence[MailCard],
    suggestion_cards: Sequence[MailCard],
    base_url: str,
    unsubscribe_token: str,
    shop_name: str,
) -> MailContent:
    """One issue for one reader: the new models, then what suits their collection."""
    sections: list[MailSection] = []
    if new_cards:
        sections.append(
            MailSection(
                heading="Neu in der Werkstatt",
                intro="Frisch gedruckt, lackiert und ab sofort im Shop:",
                cards=new_cards,
            )
        )
    if suggestion_cards:
        sections.append(
            MailSection(
                heading="Passt zu deiner Sammlung",
                intro="Ausgesucht nach deiner Spur und den Modellen, die du schon hast:",
                cards=suggestion_cards,
            )
        )
    first = new_cards[0].title if new_cards else "Neues aus der Werkstatt"
    more = len(new_cards) - 1
    tail = "" if more <= 0 else " und ein weiteres Modell" if more == 1 else f" und {more} weitere"
    subject = f"Neu bei {shop_name}: {first}{tail}"
    return MailContent(
        subject=subject,
        greeting=f"Hallo {display_name},",
        paragraphs=(
            "in der Werkstatt ist wieder einiges vom Drucker gekommen. Hier ist, was neu ist, "
            "und was wir dir dazu empfehlen.",
        ),
        sections=sections,
        action=MailAction(label="Alle Modelle ansehen", url=f"{base_url}{CATALOG_PATH}"),
        closing=(
            f"Newsletter Nr. {number}. Du bekommst ihn, weil du ihn in deinem Kundenkonto "
            "bestellt hast.",
            "Keinen Newsletter mehr? Hier mit einem Klick abmelden: "
            f"{unsubscribe_link(base_url, unsubscribe_token)}",
        ),
    )
