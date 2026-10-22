"""Identifier generation."""

import uuid

from uuid_utils.compat import uuid7


def new_id() -> uuid.UUID:
    """Return a new UUIDv7 as a standard-library :class:`uuid.UUID`.

    UUIDv7 starts with a millisecond timestamp, so identifiers sort by creation
    time. That keeps B-tree inserts local and lets the outbox be read in order.
    """
    return uuid7()
