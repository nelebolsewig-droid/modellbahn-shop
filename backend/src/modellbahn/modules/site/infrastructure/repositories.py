"""SQLAlchemy implementations of the site repositories and unit of work.

Repositories only read and stage changes; committing is the unit of work's job.
"""

from collections.abc import Sequence
from datetime import date, datetime
from functools import partial
from uuid import UUID

from sqlalchemy import delete, exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from modellbahn.modules.site.domain.model import (
    Fair,
    Mailing,
    Subscription,
    SubscriptionStatus,
)
from modellbahn.modules.site.infrastructure.mapping import start_mappers
from modellbahn.modules.site.infrastructure.tables import fairs, mailings, subscriptions
from modellbahn.platform.uow import UnitOfWork


class SqlFairRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, fair_id: UUID, *, for_update: bool = False) -> Fair | None:
        statement = select(Fair).where(fairs.c.id == fair_id)
        if for_update:
            statement = statement.with_for_update().execution_options(populate_existing=True)
        return (await self._session.scalars(statement)).one_or_none()

    async def all(self) -> Sequence[Fair]:
        statement = select(Fair).order_by(fairs.c.starts_on.desc(), fairs.c.name)
        return (await self._session.scalars(statement)).all()

    async def published_from(self, first_day: date) -> Sequence[Fair]:
        statement = (
            select(Fair)
            .where(fairs.c.published, fairs.c.ends_on >= first_day)
            .order_by(fairs.c.starts_on, fairs.c.name)
        )
        return (await self._session.scalars(statement)).all()

    async def published_before(self, day: date, limit: int) -> Sequence[Fair]:
        statement = (
            select(Fair)
            .where(fairs.c.published, fairs.c.ends_on < day)
            .order_by(fairs.c.ends_on.desc(), fairs.c.name)
            .limit(limit)
        )
        return (await self._session.scalars(statement)).all()

    def add(self, fair: Fair) -> None:
        self._session.add(fair)

    async def delete(self, fair: Fair) -> None:
        await self._session.delete(fair)


class SqlSubscriptionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def by_email(self, email: str, *, for_update: bool = False) -> Subscription | None:
        # citext: the address matches whatever its spelling.
        statement = select(Subscription).where(subscriptions.c.email == email)
        if for_update:
            statement = statement.with_for_update().execution_options(populate_existing=True)
        return (await self._session.scalars(statement)).one_or_none()

    async def get(self, subscription_id: UUID) -> Subscription | None:
        statement = (
            select(Subscription)
            .where(subscriptions.c.id == subscription_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        return (await self._session.scalars(statement)).one_or_none()

    async def by_confirm_token(self, token_hash: str) -> Subscription | None:
        statement = (
            select(Subscription)
            .where(subscriptions.c.confirm_token_hash == token_hash)
            .with_for_update()
        )
        return (await self._session.scalars(statement)).one_or_none()

    async def by_unsubscribe_token(self, token: str) -> Subscription | None:
        statement = select(Subscription).where(subscriptions.c.unsubscribe_token == token)
        return (await self._session.scalars(statement)).one_or_none()

    async def unsent(self, fair_id: UUID, limit: int) -> Sequence[Subscription]:
        already = exists().where(
            mailings.c.fair_id == fair_id, mailings.c.subscription_id == subscriptions.c.id
        )
        statement = (
            select(Subscription)
            .where(subscriptions.c.status == SubscriptionStatus.CONFIRMED, ~already)
            .order_by(subscriptions.c.created_at, subscriptions.c.id)
            .limit(limit)
        )
        return (await self._session.scalars(statement)).all()

    async def counts(self) -> dict[str, int]:
        rows = await self._session.execute(
            select(subscriptions.c.status, func.count()).group_by(subscriptions.c.status)
        )
        counted: dict[str, int] = {status.value: 0 for status in SubscriptionStatus}
        counted.update({str(status): count for status, count in rows})
        return counted

    def add(self, subscription: Subscription) -> None:
        self._session.add(subscription)

    async def delete(self, subscription: Subscription) -> None:
        await self._session.delete(subscription)

    async def delete_pending_before(self, moment: datetime) -> int:
        result = await self._session.execute(
            delete(subscriptions).where(
                subscriptions.c.status == SubscriptionStatus.PENDING,
                subscriptions.c.created_at < moment,
            )
        )
        return int(result.rowcount)  # type: ignore[attr-defined]

    def record(self, mailing: Mailing) -> None:
        self._session.add(mailing)


class SqlSiteUnitOfWork(UnitOfWork):
    """Unit of work with the site repositories attached."""

    fairs: SqlFairRepository
    subscriptions: SqlSubscriptionRepository

    def _attach(self, session: AsyncSession) -> None:
        start_mappers()
        self.fairs = SqlFairRepository(session)
        self.subscriptions = SqlSubscriptionRepository(session)


def site_uow_factory(
    session_factory: async_sessionmaker[AsyncSession],
) -> partial[SqlSiteUnitOfWork]:
    """The factory the site services get: a fresh unit of work per call."""
    return partial(SqlSiteUnitOfWork, session_factory)
