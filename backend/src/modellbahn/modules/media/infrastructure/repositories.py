"""SQLAlchemy implementations of the media repositories and unit of work.

Repositories only read and stage changes; committing is the unit of work's job.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from modellbahn.modules.media.domain.model import Asset, AssetKind, AssetStatus
from modellbahn.modules.media.infrastructure.mapping import start_mappers
from modellbahn.modules.media.infrastructure.tables import assets
from modellbahn.platform.uow import UnitOfWork


class SqlAssetRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, asset_id: UUID, *, for_update: bool = False) -> Asset | None:
        statement = select(Asset).where(assets.c.id == asset_id)
        if for_update:
            # FOR NO KEY UPDATE: does not wait for the key-share locks that a gallery
            # entry referring to the asset takes.
            statement = statement.with_for_update(key_share=True).execution_options(
                populate_existing=True
            )
        return (await self._session.execute(statement)).scalar_one_or_none()

    async def get_by_checksum(self, kind: AssetKind, sha256: str) -> Asset | None:
        statement = select(Asset).where(assets.c.kind == kind, assets.c.sha256 == sha256)
        return (await self._session.execute(statement)).scalar_one_or_none()

    def add(self, asset: Asset) -> None:
        self._session.add(asset)

    async def delete(self, asset: Asset) -> None:
        await self._session.delete(asset)

    async def stale_uploads(self, *, created_before: datetime, limit: int) -> list[Asset]:
        statement = (
            select(Asset)
            .where(
                assets.c.status == AssetStatus.PENDING_UPLOAD,
                assets.c.created_at < created_before,
            )
            .order_by(assets.c.created_at)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        return list((await self._session.execute(statement)).scalars())


class SqlMediaUnitOfWork(UnitOfWork):
    """Unit of work with the media repositories attached."""

    assets: SqlAssetRepository

    def _attach(self, session: AsyncSession) -> None:
        start_mappers()
        self.assets = SqlAssetRepository(session)
