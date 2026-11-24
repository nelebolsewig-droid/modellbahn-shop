"""Read-only facade for the newsletter: the models in the shop, as a mail shows them.

It runs SQL, so a domain layer must not import it (the pure-domain contract says so).
"""

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select

from modellbahn.modules.catalog.domain.model import ProductStatus
from modellbahn.modules.catalog.infrastructure.tables import (
    categories,
    product_media,
    product_scales,
    products,
    variants,
)
from modellbahn.platform.uow import UnitOfWork

__all__ = ["ShowcaseProduct", "load_showcase"]


@dataclass(frozen=True, slots=True)
class ShowcaseProduct:
    """A model in the shop: what a teaser needs, and what tells whom it suits."""

    product_id: UUID
    slug: str
    name: str
    summary: str
    published_at: datetime | None
    category_ids: tuple[UUID, ...]
    """The product's category and its parents, the most specific first."""
    scale_codes: tuple[str, ...]
    """Scales it is sold in (with at least one active variant)."""
    price_from_cents: int | None
    """The cheapest active variant."""
    image_asset_id: UUID | None
    """The first photo of the gallery."""


async def load_showcase(uow: UnitOfWork) -> list[ShowcaseProduct]:
    """Every product in the shop with at least one active variant, the newest first."""
    rows = (
        await uow.session.execute(
            select(
                products.c.id,
                products.c.slug,
                products.c.name,
                products.c.summary,
                products.c.published_at,
                products.c.primary_category_id,
            ).where(products.c.status == ProductStatus.ACTIVE)
        )
    ).all()
    if not rows:
        return []
    ids = [row.id for row in rows]
    scales_of: defaultdict[UUID, set[str]] = defaultdict(set)
    price_of: dict[UUID, int] = {}
    variant_rows = await uow.session.execute(
        select(
            product_scales.c.product_id,
            product_scales.c.scale_code,
            func.min(variants.c.price_cents).label("price"),
        )
        .join(variants, variants.c.product_scale_id == product_scales.c.id)
        .where(product_scales.c.product_id.in_(ids), variants.c.active)
        .group_by(product_scales.c.product_id, product_scales.c.scale_code)
    )
    for variant in variant_rows:
        scales_of[variant.product_id].add(variant.scale_code)
        cheapest = price_of.get(variant.product_id, variant.price)
        price_of[variant.product_id] = min(cheapest, variant.price)
    first_photo: dict[UUID, UUID] = {}
    photo_rows = await uow.session.execute(
        select(product_media.c.product_id, product_media.c.asset_id)
        .where(product_media.c.product_id.in_(ids))
        .order_by(product_media.c.product_id, product_media.c.position)
    )
    for photo in photo_rows:
        first_photo.setdefault(photo.product_id, photo.asset_id)
    parents: dict[UUID, UUID | None] = {
        category.id: category.parent_id
        for category in await uow.session.execute(select(categories.c.id, categories.c.parent_id))
    }

    def chain(category_id: UUID | None) -> tuple[UUID, ...]:
        found: list[UUID] = []
        while category_id is not None and category_id not in found:
            found.append(category_id)
            category_id = parents.get(category_id)
        return tuple(found)

    showcase = [
        ShowcaseProduct(
            product_id=row.id,
            slug=row.slug,
            name=row.name,
            summary=row.summary,
            published_at=row.published_at,
            category_ids=chain(row.primary_category_id),
            scale_codes=tuple(sorted(scales_of[row.id])),
            price_from_cents=price_of.get(row.id),
            image_asset_id=first_photo.get(row.id),
        )
        for row in rows
        if scales_of[row.id]
    ]
    showcase.sort(key=lambda p: (p.published_at is None, -(p.published_at or _EPOCH).timestamp()))
    return showcase


_EPOCH = datetime.fromisoformat("1970-01-01T00:00:00+00:00")
