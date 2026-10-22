"""Time source abstraction, so that time-dependent rules are testable."""

from datetime import UTC, datetime, timedelta
from typing import Protocol


class Clock(Protocol):
    """Source of the current time. Always returns timezone-aware UTC datetimes."""

    def now(self) -> datetime:
        """The current time in UTC."""
        ...


class SystemClock:
    """The real wall clock."""

    def now(self) -> datetime:
        return datetime.now(UTC)


class FixedClock:
    """A clock that only moves when told to; meant for tests."""

    def __init__(self, at: datetime) -> None:
        self._now = _require_aware(at)

    def now(self) -> datetime:
        return self._now

    def set(self, at: datetime) -> None:
        """Jump to ``at``."""
        self._now = _require_aware(at)

    def advance(self, delta: timedelta) -> None:
        """Move forward by ``delta``."""
        self._now += delta


def _require_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        msg = "FixedClock needs a timezone-aware datetime"
        raise ValueError(msg)
    return value.astimezone(UTC)
