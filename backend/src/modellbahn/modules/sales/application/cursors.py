"""Opaque page cursors: the keyset position of the last order, as URL-safe text."""

import base64
import binascii
import json
from datetime import datetime
from uuid import UUID

from modellbahn.modules.sales.application.ports import OrderCursor
from modellbahn.modules.sales.domain.errors import InvalidFieldError


def encode_cursor(cursor: OrderCursor) -> str:
    data = {"i": str(cursor.id), "p": cursor.placed_at.isoformat()}
    raw = json.dumps(data, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode_cursor(value: str) -> OrderCursor:
    """Parse a cursor from a previous page; :class:`InvalidFieldError` if it is not one."""
    try:
        padded = value + "=" * (-len(value) % 4)
        data = json.loads(base64.urlsafe_b64decode(padded.encode()))
        placed = datetime.fromisoformat(data["p"])
        if placed.tzinfo is None:
            msg = "cursor time without time zone"
            raise ValueError(msg)
        return OrderCursor(placed_at=placed, id=UUID(data["i"]))
    except (binascii.Error, ValueError, KeyError, TypeError, AttributeError) as exc:
        raise InvalidFieldError("cursor", "invalid", "not a cursor of this list") from exc
