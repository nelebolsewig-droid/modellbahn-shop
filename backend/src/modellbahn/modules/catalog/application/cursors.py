"""Opaque page cursors: the keyset position of the last product, as URL-safe text."""

import base64
import binascii
import json
from datetime import datetime
from uuid import UUID

from modellbahn.modules.catalog.application.ports import ProductCursor
from modellbahn.modules.catalog.domain.errors import InvalidFieldError


def encode_cursor(cursor: ProductCursor) -> str:
    data: dict[str, str] = {"i": str(cursor.id)}
    if cursor.published_at is not None:
        data["p"] = cursor.published_at.isoformat()
    raw = json.dumps(data, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode_cursor(value: str) -> ProductCursor:
    """Parse a cursor from a previous page; :class:`InvalidFieldError` if it is not one."""
    try:
        padded = value + "=" * (-len(value) % 4)
        data = json.loads(base64.urlsafe_b64decode(padded.encode()))
        published = None if data.get("p") is None else datetime.fromisoformat(data["p"])
        if published is not None and published.tzinfo is None:
            msg = "cursor time without time zone"
            raise ValueError(msg)
        return ProductCursor(id=UUID(data["i"]), published_at=published)
    except (binascii.Error, ValueError, KeyError, TypeError, AttributeError) as exc:
        raise InvalidFieldError("cursor", "invalid", "not a cursor of this list") from exc
