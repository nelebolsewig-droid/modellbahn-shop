"""Visitors per day: once per day and visitor, nothing about them kept past the day."""

from datetime import timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from modellbahn.modules.site.application.visits import VisitService, is_robot
from modellbahn.modules.site.infrastructure.repositories import site_uow_factory
from modellbahn.modules.site.infrastructure.tables import visit_days, visit_marks
from modellbahn.platform.clock import FixedClock

pytestmark = pytest.mark.usefixtures("clean_database")

FIREFOX = "Mozilla/5.0 (Macintosh; Intel Mac OS X 14.6; rv:132.0) Gecko/20100101 Firefox/132.0"
SAFARI = "Mozilla/5.0 (iPhone; CPU iPhone OS 18_1 like Mac OS X) AppleWebKit/605.1.15 Safari"


@pytest.fixture
def visits(session_factory: async_sessionmaker[AsyncSession], clock: FixedClock) -> VisitService:
    return VisitService(uow_factory=site_uow_factory(session_factory), clock=clock)


async def test_counts_each_visitor_once_a_day(visits: VisitService) -> None:
    for _ in range(3):
        await visits.record(address="203.0.113.7", user_agent=FIREFOX)
    await visits.record(address="203.0.113.7", user_agent=SAFARI)
    await visits.record(address="198.51.100.2", user_agent=FIREFOX)
    await visits.record(address="198.51.100.2", user_agent="Googlebot/2.1")

    [day] = await visits.last_days(1)
    assert (day.visitors, day.page_views) == (3, 5)


async def test_forgets_the_visitors_the_next_day(
    visits: VisitService, clock: FixedClock, engine: AsyncEngine
) -> None:
    await visits.record(address="203.0.113.7", user_agent=FIREFOX)
    clock.advance(timedelta(days=1))
    await visits.record(address="203.0.113.7", user_agent=FIREFOX)

    async with engine.connect() as connection:
        marks = await connection.scalar(select(func.count()).select_from(visit_marks))
        salts = await connection.scalar(
            select(func.count()).select_from(visit_days).where(visit_days.c.salt.is_not(None))
        )
    assert (marks, salts) == (1, 1)

    yesterday, today = await visits.last_days(2)
    assert (yesterday.visitors, today.visitors) == (1, 1)


async def test_days_without_visits_count_zero(visits: VisitService) -> None:
    days = await visits.last_days(30)
    assert len(days) == 30
    assert all(day.visitors == 0 for day in days)
    assert days[-1].day - days[0].day == timedelta(days=29)


def test_robots_and_empty_agents_are_no_visitors() -> None:
    assert is_robot("")
    assert is_robot("Mozilla/5.0 (compatible; bingbot/2.0)")
    assert is_robot("WhatsApp/2.23")
    assert not is_robot(FIREFOX)
