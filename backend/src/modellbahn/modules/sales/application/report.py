"""The sales report (*Verkäufe*, ADR 0039): what was sold in a span of days, on every channel.

Two sources make one list. Online orders count with their lines on the day they were
paid, unless cancelled since (a cancelled paid order was refunded in full). Pieces sold
outside the shop, at a fair, on site or privately, count on the day they were booked out
as sold, at the price entered for them; without one at today's shop price, marked as such.

Days are shop days (Europe/Berlin), so a sale at 23:30 belongs to that evening's fair day.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Final

from modellbahn.modules.sales.application.common import UnitOfWorkFactory
from modellbahn.modules.sales.application.mails import SHOP_TIME_ZONE
from modellbahn.modules.sales.application.ports import SoldLine
from modellbahn.modules.sales.domain.errors import InvalidFieldError

REPORT_DAYS_MAX: Final = 366


@dataclass(frozen=True, slots=True)
class SalesReport:
    start: date
    end: date
    """Inclusive."""
    lines: Sequence[SoldLine]
    """The latest first."""


def shop_day_bounds(start: date, end: date) -> tuple[datetime, datetime]:
    """``[start 00:00, day after end 00:00)`` in shop time."""
    since = datetime.combine(start, time.min, tzinfo=SHOP_TIME_ZONE)
    until = datetime.combine(end + timedelta(days=1), time.min, tzinfo=SHOP_TIME_ZONE)
    return since, until


def check_span(start: date, end: date) -> None:
    if end < start:
        raise InvalidFieldError("end", "before_start", "not before the start")
    if (end - start).days + 1 > REPORT_DAYS_MAX:
        raise InvalidFieldError("end", "out_of_range", f"at most {REPORT_DAYS_MAX} days")


class SalesReportService:
    def __init__(self, *, uow_factory: UnitOfWorkFactory) -> None:
        self._uow = uow_factory

    async def report(self, start: date, end: date) -> SalesReport:
        check_span(start, end)
        since, until = shop_day_bounds(start, end)
        async with self._uow() as uow:
            lines = await uow.sales_ledger.sold(since, until)
        lines.sort(key=lambda line: (line.sold_at, line.key), reverse=True)
        return SalesReport(start=start, end=end, lines=lines)
