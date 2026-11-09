"""SQLAlchemy implementations of the AI repositories, the facts source and the unit of work.

Repositories only read and stage changes; committing is the unit of work's job.
"""

import ipaddress
import urllib.parse
from collections.abc import Sequence
from datetime import datetime
from decimal import Decimal
from functools import partial
from typing import Final
from uuid import UUID

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from modellbahn.modules.ai.application.ports import CopyFacts
from modellbahn.modules.ai.domain.model import MAX_ATTEMPTS, AiRun, Review, RunStatus
from modellbahn.modules.ai.infrastructure.mapping import start_mappers
from modellbahn.modules.ai.infrastructure.tables import runs
from modellbahn.modules.catalog.contracts.copy_facts import (
    CopySource,
    load_copy_source,
    load_draft_products,
)
from modellbahn.modules.media.contracts.images import ImageView, load_images
from modellbahn.platform.events import JsonObject, JsonValue
from modellbahn.platform.uow import UnitOfWork

MAX_PHOTOS: Final = 2
"""The main photo and one more: enough to see colour and form, little to pay for."""
_PHOTO_SIZES: Final = ("lg", "md", "xl", "sm")
AVERAGE_OVER: Final = 50
"""The cost estimate of a draft averages this many of the latest."""


class SqlRunRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, run_id: UUID, *, for_update: bool = False) -> AiRun | None:
        statement = select(AiRun).where(runs.c.id == run_id)
        if for_update:
            statement = statement.with_for_update().execution_options(populate_existing=True)
        return (await self._session.scalars(statement)).one_or_none()

    async def next_due(self, *, stale_before: datetime) -> AiRun | None:
        statement = (
            select(AiRun)
            .where(
                or_(
                    and_(runs.c.status == RunStatus.QUEUED, runs.c.review == Review.PENDING),
                    and_(runs.c.status == RunStatus.RUNNING, runs.c.started_at < stale_before),
                ),
                runs.c.attempts <= MAX_ATTEMPTS,
            )
            .order_by(runs.c.created_at)
            .limit(1)
            .with_for_update(skip_locked=True)
            .execution_options(populate_existing=True)
        )
        return (await self._session.scalars(statement)).one_or_none()

    async def open_for(self, product_ids: Sequence[UUID]) -> dict[UUID, AiRun]:
        if not product_ids:
            return {}
        statement = (
            select(AiRun)
            .where(
                runs.c.product_id.in_(list(product_ids)),
                or_(
                    runs.c.status.in_([RunStatus.QUEUED, RunStatus.RUNNING]),
                    and_(runs.c.status == RunStatus.DONE, runs.c.review == Review.PENDING),
                ),
            )
            .order_by(runs.c.created_at)
        )
        found: dict[UUID, AiRun] = {}
        for run in (await self._session.scalars(statement)).all():
            if run.product_id is not None:
                found[run.product_id] = run  # the newest wins
        return found

    async def recent(
        self, *, limit: int, product_id: UUID | None = None, review: Review | None = None
    ) -> Sequence[AiRun]:
        statement = select(AiRun).order_by(runs.c.created_at.desc(), runs.c.id).limit(limit)
        if product_id is not None:
            statement = statement.where(runs.c.product_id == product_id)
        if review is not None:
            statement = statement.where(runs.c.review == review)
        return (await self._session.scalars(statement)).all()

    async def spent_since(self, moment: datetime) -> int:
        total = await self._session.scalar(
            select(func.coalesce(func.sum(runs.c.cost_micro_usd), 0)).where(
                runs.c.created_at >= moment
            )
        )
        return int(total or 0)

    async def average_cost(self) -> int | None:
        latest = (
            select(runs.c.cost_micro_usd)
            .where(runs.c.status == RunStatus.DONE, runs.c.cost_micro_usd > 0)
            .order_by(runs.c.finished_at.desc())
            .limit(AVERAGE_OVER)
            .subquery()
        )
        average = await self._session.scalar(select(func.avg(latest.c.cost_micro_usd)))
        return round(average) if average is not None else None

    def add(self, run: AiRun) -> None:
        self._session.add(run)


class SqlFactsSource:
    """The product facts from the catalogue's contract, photos from the media contract."""

    def __init__(self, uow: UnitOfWork, *, site_url: str, media_base_url: str) -> None:
        self._uow = uow
        self._site_url = site_url
        self._media_base_url = media_base_url

    async def copy_facts(self, product_id: UUID) -> CopyFacts | None:
        source = await load_copy_source(self._uow, product_id)
        if source is None:
            return None
        images = await load_images(
            self._uow, source.image_ids, public_base_url=self._media_base_url
        )
        urls = [
            url
            for asset_id in source.image_ids
            if (view := images.get(asset_id)) is not None and (url := self._photo_url(view))
        ]
        return CopyFacts(
            product_id=source.product_id,
            name=source.name,
            facts=facts_of(source, photos=len(source.image_ids)),
            image_urls=tuple(urls[:MAX_PHOTOS]),
        )

    async def draft_products(self) -> Sequence[tuple[UUID, str]]:
        return await load_draft_products(self._uow)

    def _photo_url(self, view: ImageView) -> str | None:
        """A WebP of a sensible size at a public https address the model can fetch."""
        if not view.is_ready:
            return None
        by_name = {r.name: r for r in view.renditions if r.format.value == "webp"}
        rendition = next((by_name[n] for n in _PHOTO_SIZES if n in by_name), None)
        if rendition is None:
            return None
        url = rendition.url
        if url.startswith("/"):
            url = f"{self._site_url}{url}"
        return url if is_public_https(url) else None


def is_public_https(url: str) -> bool:
    """True for https addresses outside this machine and its network (dev stays local)."""
    parts = urllib.parse.urlsplit(url)
    host = (parts.hostname or "").lower()
    if parts.scheme != "https" or not host or host == "localhost" or host.endswith(".localhost"):
        return False
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return "." in host
    return address.is_global


def _number(value: Decimal | int | None) -> JsonValue:
    if value is None:
        return None
    if isinstance(value, Decimal):
        normal = value.normalize()
        return format(normal, "f")
    return value


def facts_of(source: CopySource, *, photos: int) -> JsonObject:
    """The facts as the model sees them, with German keys (the prompt is German too)."""
    return {
        "name": source.name,
        "kategorie": source.category_path,
        "vorbild": source.prototype,
        "epochen": list(source.epochs),
        "massstaebe": [
            {
                "massstab": scale.name,
                "verhaeltnis": scale.ratio,
                "spurweite_mm": _number(scale.track_gauge_mm),
                "laenge_mm": _number(scale.length_mm),
                "breite_mm": _number(scale.width_mm),
                "hoehe_mm": _number(scale.height_mm),
                "gewicht_g": _number(scale.weight_g),
                "ausfuehrungen": list(scale.finishes),
                "farben": list(scale.colors),
            }
            for scale in source.scales
        ],
        "bisheriger_kurztext": source.summary,
        "bisherige_beschreibung": source.description,
        "fotos": photos,
    }


class SqlAiUnitOfWork(UnitOfWork):
    """Unit of work with the runs and the product facts attached."""

    runs: SqlRunRepository
    facts: SqlFactsSource

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        site_url: str,
        media_base_url: str,
    ) -> None:
        super().__init__(session_factory)
        self._site_url = site_url
        self._media_base_url = media_base_url

    def _attach(self, session: AsyncSession) -> None:
        self.runs = SqlRunRepository(session)
        self.facts = SqlFactsSource(
            self, site_url=self._site_url, media_base_url=self._media_base_url
        )


def ai_uow_factory(
    session_factory: async_sessionmaker[AsyncSession], *, site_url: str, media_base_url: str
) -> partial[SqlAiUnitOfWork]:
    """Factory for the AI use cases: a new unit of work per call."""
    start_mappers()
    return partial(
        SqlAiUnitOfWork, session_factory, site_url=site_url, media_base_url=media_base_url
    )
