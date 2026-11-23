"""Short WhatsApp notes to the team (ADR 0045), sent through CallMeBot.

CallMeBot is a free relay for messages to one's own phone: each person sends it one
WhatsApp once and gets a key back. Only internal notes go this way, no customer data.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final, Protocol

import httpx
import structlog

_logger = structlog.get_logger(__name__)

CALLMEBOT_URL: Final = "https://api.callmebot.com/whatsapp.php"


@dataclass(frozen=True, slots=True)
class WhatsAppRecipient:
    phone: str
    """International format, e.g. +491701234567."""
    api_key: str


def parse_recipients(raw: str) -> tuple[WhatsAppRecipient, ...]:
    """``+491701234567:KEY,+491609876543:KEY`` → recipients; blanks and junk are skipped."""
    found: dict[str, WhatsAppRecipient] = {}
    for entry in raw.split(","):
        phone, _, key = entry.partition(":")
        phone = "".join(phone.split()).replace("/", "").replace("-", "")
        if phone.startswith("00"):
            phone = "+" + phone[2:]
        if phone and key.strip():
            found.setdefault(phone, WhatsAppRecipient(phone=phone, api_key=key.strip()))
    return tuple(found.values())


class Messenger(Protocol):
    """Sends one short text to every configured phone. Never raises: a note is a
    courtesy beside the mail, and the mail must not go out twice because of it."""

    async def send(self, text: str) -> None: ...


class CallMeBotWhatsApp:
    def __init__(
        self,
        recipients: Sequence[WhatsAppRecipient],
        *,
        url: str = CALLMEBOT_URL,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._recipients = tuple(recipients)
        self._url = url
        self._transport = transport

    async def send(self, text: str) -> None:
        async with httpx.AsyncClient(timeout=httpx.Timeout(20.0), transport=self._transport) as c:
            for recipient in self._recipients:
                try:
                    response = await c.get(
                        self._url,
                        params={
                            "phone": recipient.phone,
                            "text": text,
                            "apikey": recipient.api_key,
                        },
                    )
                    response.raise_for_status()
                except httpx.HTTPError as exc:
                    _logger.warning(
                        "whatsapp.send_failed",
                        phone_end=recipient.phone[-3:],
                        error=type(exc).__name__,
                    )


class InMemoryMessenger:
    """Test double: keeps what was sent."""

    def __init__(self) -> None:
        self.sent: list[str] = []

    async def send(self, text: str) -> None:
        self.sent.append(text)
