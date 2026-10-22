"""The German e-mails of the identity module (content only; the layout is in ``platform.mail``)."""

from typing import Final
from urllib.parse import urlencode

from modellbahn.modules.identity.domain.model import Account
from modellbahn.platform.mail import MailAction, MailContent

VERIFY_PATH: Final = "/konto/bestaetigen"
FORGOT_PASSWORD_PATH: Final = "/konto/passwort-vergessen"  # noqa: S105
RESET_PASSWORD_PATH: Final = "/konto/passwort-zuruecksetzen"  # noqa: S105


def link(base_url: str, path: str, *, token: str | None = None) -> str:
    """Absolute link into the shop frontend, optionally carrying a one-time token."""
    query = f"?{urlencode({'token': token})}" if token is not None else ""
    return f"{base_url}{path}{query}"


def verification_mail(
    account: Account, *, base_url: str, token: str, shop_name: str
) -> MailContent:
    return MailContent(
        subject="Bitte bestätige deine E-Mail-Adresse",
        greeting=f"Hallo {account.display_name},",
        paragraphs=(
            f"willkommen bei {shop_name}! Bitte bestätige deine E-Mail-Adresse, "
            "damit wir dein Kundenkonto freischalten können.",
            "Der Link ist 24 Stunden gültig und meldet dich gleich an.",
        ),
        action=MailAction(
            label="E-Mail-Adresse bestätigen", url=link(base_url, VERIFY_PATH, token=token)
        ),
        closing=(
            "Falls du dich nicht registriert hast, kannst du diese E-Mail einfach ignorieren. "
            "Ohne Bestätigung wird das Konto nicht freigeschaltet.",
        ),
    )


def existing_account_mail(account: Account, *, base_url: str, shop_name: str) -> MailContent:
    return MailContent(
        subject="Für diese Adresse gibt es schon ein Konto",
        greeting=f"Hallo {account.display_name},",
        paragraphs=(
            f"gerade wollte sich jemand mit dieser E-Mail-Adresse bei {shop_name} registrieren. "
            "Für diese Adresse gibt es aber schon ein Kundenkonto.",
            "Wenn du das warst und dein Passwort nicht mehr weißt, kannst du ein neues festlegen:",
        ),
        action=MailAction(label="Passwort zurücksetzen", url=link(base_url, FORGOT_PASSWORD_PATH)),
        closing=(
            "Wenn du das nicht warst, kannst du diese E-Mail ignorieren. "
            "An deinem Konto hat sich nichts geändert.",
        ),
    )


def password_reset_mail(account: Account, *, base_url: str, token: str) -> MailContent:
    return MailContent(
        subject="Neues Passwort festlegen",
        greeting=f"Hallo {account.display_name},",
        paragraphs=(
            "du hast ein neues Passwort für dein Kundenkonto angefordert.",
            "Der Link ist eine Stunde gültig und funktioniert nur einmal.",
        ),
        action=MailAction(
            label="Neues Passwort festlegen", url=link(base_url, RESET_PASSWORD_PATH, token=token)
        ),
        closing=(
            "Wenn du das nicht angefordert hast, kannst du diese E-Mail ignorieren. "
            "Dein bisheriges Passwort bleibt gültig.",
        ),
    )


def password_changed_mail(account: Account, *, base_url: str, shop_name: str) -> MailContent:
    paragraphs = (f"das Passwort deines Kontos bei {shop_name} wurde geändert.",)
    if account.is_customer:
        return MailContent(
            subject="Dein Passwort wurde geändert",
            greeting=f"Hallo {account.display_name},",
            paragraphs=(
                *paragraphs,
                "Wenn du das nicht warst, setze dein Passwort bitte sofort zurück:",
            ),
            action=MailAction(
                label="Passwort zurücksetzen", url=link(base_url, FORGOT_PASSWORD_PATH)
            ),
            closing=("Wenn du das selbst warst, ist alles in Ordnung.",),
        )
    return MailContent(
        subject="Dein Passwort wurde geändert",
        greeting=f"Hallo {account.display_name},",
        paragraphs=(
            *paragraphs,
            "Wenn du das nicht warst, wende dich bitte sofort an die Shop-Leitung.",
        ),
        closing=("Wenn du das selbst warst, ist alles in Ordnung.",),
    )
