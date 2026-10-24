"""Read-only facade for images, for other modules' application and infrastructure layers.

It runs SQL, so a domain layer must not import it (the pure-domain contract says so).
"""

from collections import defaultdict
from collections.abc import Collection
from dataclasses import dataclass
from typing import Final
from uuid import UUID

from sqlalchemy import select

from modellbahn.modules.media.domain.errors import FailureCode
from modellbahn.modules.media.domain.model import AssetKind, AssetStatus
from modellbahn.modules.media.domain.renditions import RenditionFormat
from modellbahn.modules.media.infrastructure.tables import assets, image_details, renditions
from modellbahn.platform.uow import UnitOfWork

__all__ = [
    "IMAGE_KIND",
    "IMAGE_REFERENCE",
    "AssetStatus",
    "ImageRendition",
    "ImageView",
    "RenditionFormat",
    "load_images",
]

IMAGE_REFERENCE: Final = ("media.assets.id", "media.assets.kind")
"""Target of a composite foreign key ``(asset_id, asset_kind)`` that only accepts images.

The referring table keeps ``asset_kind`` fixed to :data:`IMAGE_KIND` with a CHECK.
Importing this also puts the media tables on the shared metadata, which SQLAlchemy
needs to resolve the key. Deleting a referred asset fails (``RESTRICT``)."""

IMAGE_KIND: Final = AssetKind.IMAGE.value


@dataclass(frozen=True, slots=True)
class ImageRendition:
    """One rendered size; ``url`` is ready for an ``<img>`` or ``srcset``."""

    name: str
    format: RenditionFormat
    width: int
    height: int
    url: str


@dataclass(frozen=True, slots=True)
class ImageView:
    """An image as other modules may show it. Facts and sizes exist once it is ready."""

    asset_id: UUID
    status: AssetStatus
    filename: str
    failure_code: FailureCode | None
    width: int | None
    height: int | None
    dominant_color: str | None
    lqip: str | None
    renditions: tuple[ImageRendition, ...]

    @property
    def is_ready(self) -> bool:
        return self.status is AssetStatus.READY


async def load_images(
    uow: UnitOfWork, asset_ids: Collection[UUID], *, public_base_url: str
) -> dict[UUID, ImageView]:
    """The images among ``asset_ids``, read inside the caller's unit of work.

    Unknown ids and assets of other kinds are missing from the result. URLs are
    ``{public_base_url}/{storage key}``.
    """
    ids = list(set(asset_ids))
    if not ids:
        return {}
    rows = (
        await uow.session.execute(
            select(
                assets.c.id,
                assets.c.status,
                assets.c.original_filename,
                assets.c.failure_code,
                image_details.c.width,
                image_details.c.height,
                image_details.c.dominant_color,
                image_details.c.lqip,
            )
            .outerjoin(image_details, image_details.c.asset_id == assets.c.id)
            .where(assets.c.id.in_(ids), assets.c.kind == AssetKind.IMAGE)
        )
    ).all()
    sizes: defaultdict[UUID, list[ImageRendition]] = defaultdict(list)
    rendition_rows = await uow.session.execute(
        select(
            renditions.c.asset_id,
            renditions.c.name,
            renditions.c.format,
            renditions.c.width,
            renditions.c.height,
            renditions.c.storage_key,
        )
        .where(renditions.c.asset_id.in_([row.id for row in rows]))
        .order_by(renditions.c.asset_id, renditions.c.width, renditions.c.format)
    )
    for rendition in rendition_rows:
        sizes[rendition.asset_id].append(
            ImageRendition(
                name=rendition.name,
                format=rendition.format,
                width=rendition.width,
                height=rendition.height,
                url=f"{public_base_url}/{rendition.storage_key}",
            )
        )
    return {
        row.id: ImageView(
            asset_id=row.id,
            status=row.status,
            filename=row.original_filename,
            failure_code=row.failure_code,
            width=row.width,
            height=row.height,
            dominant_color=row.dominant_color,
            lqip=row.lqip,
            renditions=tuple(sizes[row.id]),
        )
        for row in rows
    }
