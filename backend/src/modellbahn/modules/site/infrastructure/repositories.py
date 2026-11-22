"""SQLAlchemy implementations of the site repositories and unit of work.

Repositories only read and stage changes; committing is the unit of work's job.
"""

from collections.abc import Collection, Sequence
from datetime import date, datetime
from functools import partial
from uuid import UUID

from sqlalchemy import delete, exists, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from modellbahn.modules.media.contracts.images import ImageView, load_images
from modellbahn.modules.site.domain.model import (
    Fair,
    Mailing,
    Subscription,
    SubscriptionStatus,
    VisitDay,
)
from modellbahn.modules.site.infrastructure.mapping import start_mappers
from modellbahn.modules.site.infrastructure.tables import (
    fairs,
    mailings,
    subscriptions,
    visit_days,
    visit_marks,
)
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


class SqlVisitRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def salt(self, day: date, fresh: bytes) -> tuple[bytes, bool]:
        created = await self._session.scalar(
            insert(visit_days)
            .values(day=day, salt=fresh, visitors=0, page_views=0)
            .on_conflict_do_nothing()
            .returning(visit_days.c.day)
        )
        if created is not None:
            return fresh, True
        salt = await self._session.scalar(select(visit_days.c.salt).where(visit_days.c.day == day))
        return bytes(salt or fresh), False

    async def forget_before(self, day: date) -> None:
        await self._session.execute(delete(visit_marks).where(visit_marks.c.day < day))
        await self._session.execute(
            update(visit_days)
            .where(visit_days.c.day < day, visit_days.c.salt.is_not(None))
            .values(salt=None)
        )

    async def mark(self, day: date, mark: str) -> bool:
        noted = await self._session.scalar(
            insert(visit_marks)
            .values(day=day, mark=mark)
            .on_conflict_do_nothing()
            .returning(visit_marks.c.mark)
        )
        return noted is not None

    async def count(self, day: date, *, new_visitor: bool) -> None:
        await self._session.execute(
            update(visit_days)
            .where(visit_days.c.day == day)
            .values(
                page_views=visit_days.c.page_views + 1,
                visitors=visit_days.c.visitors + (1 if new_visitor else 0),
            )
        )

    async def between(self, first: date, last: date) -> Sequence[VisitDay]:
        rows = await self._session.execute(
            select(visit_days.c.day, visit_days.c.visitors, visit_days.c.page_views)
            .where(visit_days.c.day.between(first, last))
            .order_by(visit_days.c.day)
        )
        return [
            VisitDay(day=day, visitors=visitors, page_views=views) for day, visitors, views in rows
        ]


class SqlImages:
    """The media module's image facade, inside this unit of work's transaction."""

    def __init__(self, uow: UnitOfWork, public_base_url: str) -> None:
        self._uow = uow
        self._public_base_url = public_base_url

    async def load(self, asset_ids: Collection[UUID]) -> dict[UUID, ImageView]:
        return await load_images(self._uow, asset_ids, public_base_url=self._public_base_url)


class SqlSiteUnitOfWork(UnitOfWork):
    """Unit of work with the site repositories attached."""

    fairs: SqlFairRepository
    subscriptions: SqlSubscriptionRepository
    visits: SqlVisitRepository
    images: SqlImages

    def __init__(
        self, session_factory: async_sessionmaker[AsyncSession], *, public_base_url: str = ""
    ) -> None:
        super().__init__(session_factory)
        self._public_base_url = public_base_url

    def _attach(self, session: AsyncSession) -> None:
        start_mappers()
        self.fairs = SqlFairRepository(session)
        self.subscriptions = SqlSubscriptionRepository(session)
        self.visits = SqlVisitRepository(session)
        self.images = SqlImages(self, self._public_base_url)


def site_uow_factory(
    session_factory: async_sessionmaker[AsyncSession], *, public_base_url: str = ""
) -> partial[SqlSiteUnitOfWork]:
    """The factory the site services get: a fresh unit of work per call.

    ``public_base_url`` prefixes the image URLs (the media storage's public address)."""
    return partial(SqlSiteUnitOfWork, session_factory, public_base_url=public_base_url)
