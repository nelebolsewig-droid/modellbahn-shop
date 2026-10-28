"""Dates as the shop writes them: German, without the year twice."""

from datetime import date
from typing import Final

# The dash of date ranges, as in print (written as an escape: it looks like a hyphen).
EN_DASH: Final = "\u2013"

MONTHS: Final = (
    "Januar",
    "Februar",
    "März",
    "April",
    "Mai",
    "Juni",
    "Juli",
    "August",
    "September",
    "Oktober",
    "November",
    "Dezember",
)


def long_date(day: date) -> str:
    """``7. November 2026``."""
    return f"{day.day}. {MONTHS[day.month - 1]} {day.year}"


def date_range(start: date, end: date) -> str:
    """``7. November 2026``, ``20.-22. November 2026`` or ``30. Oktober - 1. November 2026``,
    each with an en dash instead of the hyphen."""
    if start == end:
        return long_date(start)
    if start.year != end.year:
        return f"{long_date(start)} {EN_DASH} {long_date(end)}"
    if start.month != end.month:
        return f"{start.day}. {MONTHS[start.month - 1]} {EN_DASH} {long_date(end)}"
    return f"{start.day}.{EN_DASH}{long_date(end)}"
