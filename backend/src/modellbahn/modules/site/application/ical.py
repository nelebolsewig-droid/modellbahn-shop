"""The fairs as an iCalendar file (RFC 5545), for "add to calendar" and subscribed feeds.

All-day events: ``DTSTART;VALUE=DATE`` and an exclusive ``DTEND`` the day after the
last fair day. Lines end in CRLF and are folded at 75 octets.
"""

from collections.abc import Iterable, Sequence
from datetime import UTC, datetime, timedelta
from typing import Final
from urllib.parse import urlsplit

from modellbahn.modules.site.domain.model import Fair

_FOLD_AT: Final = 75


def _escape(text: str) -> str:
    return (
        text.replace("\\", "\\\\")
        .replace(";", r"\;")
        .replace(",", "\\,")
        .replace("\r\n", "\\n")
        .replace("\n", "\\n")
    )


def _fold(line: str) -> str:
    """Split ``line`` into octet-limited pieces, never inside a UTF-8 character."""
    pieces: list[str] = []
    current = ""
    limit = _FOLD_AT
    for char in line:
        if len((current + char).encode()) > limit:
            pieces.append(current)
            current = char
            limit = _FOLD_AT - 1  # continuation lines start with a space
        else:
            current += char
    pieces.append(current)
    return "\r\n ".join(pieces)


def _stamp(moment: datetime) -> str:
    return moment.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")


def _event(fair: Fair, *, shop_name: str, base_url: str, host: str) -> list[str]:
    details = [
        *([f"Stand: {fair.booth}"] if fair.booth else []),
        *([f"Geöffnet: {fair.hours}"] if fair.hours else []),
        *([fair.note] if fair.note else []),
        f"Alle Termine: {base_url}/termine",
    ]
    return [
        "BEGIN:VEVENT",
        f"UID:fair-{fair.id}@{host}",
        f"DTSTAMP:{_stamp(fair.updated_at)}",
        f"LAST-MODIFIED:{_stamp(fair.updated_at)}",
        f"DTSTART;VALUE=DATE:{fair.starts_on:%Y%m%d}",
        f"DTEND;VALUE=DATE:{fair.ends_on + timedelta(days=1):%Y%m%d}",
        f"SUMMARY:{_escape(f'{shop_name} auf der Messe: {fair.name}')}",
        f"LOCATION:{_escape(fair.place())}",
        f"DESCRIPTION:{_escape(chr(10).join(details))}",
        f"URL:{fair.website_url or f'{base_url}/termine'}",
        "TRANSP:TRANSPARENT",
        "END:VEVENT",
    ]


def calendar(fairs: Iterable[Fair], *, shop_name: str, base_url: str) -> str:
    """A calendar with one all-day event per fair."""
    host = urlsplit(base_url).hostname or "localhost"
    lines: Sequence[str] = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        f"PRODID:-//{_escape(shop_name)}//Messetermine//DE",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{_escape(f'{shop_name} auf Messen')}",
        "X-WR-TIMEZONE:Europe/Berlin",
        *(
            line
            for fair in fairs
            for line in _event(fair, shop_name=shop_name, base_url=base_url, host=host)
        ),
        "END:VCALENDAR",
    ]
    return "".join(f"{_fold(line)}\r\n" for line in lines)
