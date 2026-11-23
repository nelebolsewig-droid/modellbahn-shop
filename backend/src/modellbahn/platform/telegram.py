"""Short Telegram notes to the team (ADR 0045): a bot of our own posts into chats we name.

Set up once with @BotFather (bot token) and the bot added to a group; the group's chat
id comes from the bot's getUpdates. Only internal notes go this way, no customer data.
"""

from collections.abc import Sequence
from typing import Final

import httpx
import structlog

_logger = structlog.get_logger(__name__)

TELEGRAM_API: Final = "https://api.telegram.org"


def parse_chat_ids(raw: str) -> tuple[str, ...]:
    """``-1001234567890, 98765`` → the chat ids, blanks and duplicates skipped."""
    found: dict[str, None] = {}
    for entry in raw.split(","):
        if chat := entry.strip():
            found.setdefault(chat)
    return tuple(found)


class TelegramBot:
    """Sends one plain text to every chat; a failure is logged, never raised."""

    def __init__(
        self,
        token: str,
        chat_ids: Sequence[str],
        *,
        api: str = TELEGRAM_API,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._url = f"{api}/bot{token}/sendMessage"
        self._chat_ids = tuple(chat_ids)
        self._transport = transport

    async def send(self, text: str) -> None:
        plain = text.replace("*", "")  # WhatsApp's bold marks; Telegram gets plain text
        async with httpx.AsyncClient(timeout=httpx.Timeout(20.0), transport=self._transport) as c:
            for chat_id in self._chat_ids:
                try:
                    response = await c.post(
                        self._url,
                        json={"chat_id": chat_id, "text": plain, "disable_web_page_preview": True},
                    )
                    response.raise_for_status()
                except httpx.HTTPError as exc:
                    # Never log the URL: it carries the bot token.
                    _logger.warning(
                        "telegram.send_failed", chat=chat_id[-4:], error=type(exc).__name__
                    )
