"""SQLAlchemy implementations of the newsletter repositories and unit of work.

Repositories only read and stage changes; committing is the unit of work's job.
"""

from collections.abc import Collection, Sequence
from datetime import datetime
from functools import partial
from uuid import UUID

from sqlalchemy import delete, exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from modellbahn.modules.catalog.contracts.showcase import ShowcaseProduct, load_showcase
from modellbahn.modules.identity.contracts.accounts import AccountSummary, get_account_summary
from modellbahn.modules.media.contracts.images import ImageView, load_images
from modellbahn.modules.newsletter.domain.model import (
    Delivery,
    Issue,
    Subscription,
    SubscriptionStatus,
)
from modellbahn.modules.newsletter.infrastructure.mapping import start_mappers
from modellbahn.modules.newsletter.infrastructure.tables import deliveries, issues, subscriptions
from modellbahn.modules.sales.contracts.purchases import Purchase, load_purchases
from modellbahn.platform.uow import UnitOfWork


class SqlSubscriptionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, subscription_id: UUID) -> Subscription | None:
        statement = (
            select(Subscription)
            .where(subscriptions.c.id == subscription_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        return (await self._session.scalars(statement)).one_or_none()

    async def by_account(
        self, account_id: UUID, *, for_update: bool = False
    ) -> Subscription | None:
        statement = select(Subscription).where(subscriptions.c.account_id == account_id)
        if for_update:
            statement = statement.with_for_update().execution_options(populate_existing=True)
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

    async def unsent(self, issue_id: UUID, limit: int) -> Sequence[Subscription]:
        already = exists().where(
            deliveries.c.issue_id == issue_id,
            deliveries.c.subscription_id == subscriptions.c.id,
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
                subscriptions.c.confirm_requested_at < moment,
            )
        )
        return int(result.rowcount)  # type: ignore[attr-defined]

    def record(self, delivery: Delivery) -> None:
        self._session.add(delivery)


class SqlIssueRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, issue_id: UUID) -> Issue | None:
        return await self._session.get(Issue, issue_id)

    async def latest(self) -> Issue | None:
        statement = select(Issue).order_by(issues.c.number.desc()).limit(1)
        return (await self._session.scalars(statement)).one_or_none()

    async def recent(self, limit: int) -> Sequence[tuple[Issue, int]]:
        sent = (
            select(func.count())
            .where(deliveries.c.issue_id == issues.c.id)
            .scalar_subquery()
            .label("sent")
        )
        rows = await self._session.execute(
            select(Issue, sent).order_by(issues.c.number.desc()).limit(limit)
        )
        return [(row[0], int(row[1])) for row in rows]

    def add(self, issue: Issue) -> None:
        self._session.add(issue)


class SqlShop:
    """The other modules' contracts, read in this unit of work's transaction."""

    def __init__(self, uow: UnitOfWork, public_base_url: str) -> None:
        self._uow = uow
        self._public_base_url = public_base_url

    async def showcase(self) -> list[ShowcaseProduct]:
        return await load_showcase(self._uow)

    async def purchases(self, account_id: UUID) -> frozenset[Purchase]:
        return await load_purchases(self._uow, account_id)

    async def account(self, account_id: UUID) -> AccountSummary | None:
        return await get_account_summary(self._uow, account_id)

    async def images(self, asset_ids: Collection[UUID]) -> dict[UUID, ImageView]:
        return await load_images(self._uow, asset_ids, public_base_url=self._public_base_url)


class SqlNewsletterUnitOfWork(UnitOfWork):
    """Unit of work with the newsletter repositories attached."""

    subscriptions: SqlSubscriptionRepository
    issues: SqlIssueRepository
    shop: SqlShop

    def __init__(
        self, session_factory: async_sessionmaker[AsyncSession], *, public_base_url: str = ""
    ) -> None:
        super().__init__(session_factory)
        self._public_base_url = public_base_url

    def _attach(self, session: AsyncSession) -> None:
        start_mappers()
        self.subscriptions = SqlSubscriptionRepository(session)
        self.issues = SqlIssueRepository(session)
        self.shop = SqlShop(self, self._public_base_url)


def newsletter_uow_factory(
    session_factory: async_sessionmaker[AsyncSession], *, public_base_url: str = ""
) -> partial[SqlNewsletterUnitOfWork]:
    """A fresh unit of work per call; ``public_base_url`` prefixes the image URLs (it must
    be absolute here: the photos are shown in mail programs)."""
    return partial(SqlNewsletterUnitOfWork, session_factory, public_base_url=public_base_url)
