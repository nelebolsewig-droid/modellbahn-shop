"""Read-only facade for the variants the shop sells, for the sales module.

It runs SQL, so a domain layer must not import it (the pure-domain contract says so).
"""

from collections import defaultdict
from collections.abc import Collection
from dataclasses import dataclass
from typing import Final
from uuid import UUID

from sqlalchemy import ColumnElement, select

from modellbahn.modules.catalog.domain.model import ProductStatus
from modellbahn.modules.catalog.infrastructure.tables import (
    finishes,
    product_media,
    product_scales,
    products,
    scales,
    variants,
)
from modellbahn.platform.uow import UnitOfWork

__all__ = [
    "VARIANT_REFERENCE",
    "SaleVariant",
    "load_product_variants",
    "load_sale_variants",
    "load_variant_by_gtin",
]

VARIANT_REFERENCE: Final = "catalog.variants.id"
"""Target for another module's foreign key to a variant (``RESTRICT``: a variant with
stock cannot be deleted). Importing it also puts the catalogue tables on the shared
metadata, which SQLAlchemy needs to resolve the key."""


@dataclass(frozen=True, slots=True)
class SaleVariant:
    """What a cart and an order need to know about a variant, as it is right now."""

    variant_id: UUID
    gtin: str
    product_id: UUID
    product_slug: str
    product_name: str
    scale_code: str
    scale_name: str
    finish_code: str
    finish_name: str
    color: str
    """Empty for a kit and for a finished model in one colour only."""
    sku: str
    price_cents: int
    compare_at_price_cents: int | None
    image_asset_id: UUID | None
    """The gallery image that fits scale, finish and colour best (else an untagged one)."""
    purchasable: bool
    """In the shop and active: only such variants go into a cart and into an order."""
    allow_backorder: bool
    """Made to order: may be sold without stock, the workshop makes it for the customer."""
    lead_time_weeks: tuple[int, int] | None
    """How many weeks making it takes (from, to); set for every variant made to order."""

    @property
    def variant_name(self) -> str:
        """``H0 · Fertigmodell, Gelb``: the variant without the product's name."""
        finish = f"{self.finish_name}, {self.color}" if self.color else self.finish_name
        return f"{self.scale_name} · {finish}"

    @property
    def title(self) -> str:
        """``IFA ADK 70 Autokran · H0 · Fertigmodell, Gelb``, as an order line freezes it."""
        return f"{self.product_name} · {self.variant_name}"


async def load_sale_variants(
    uow: UnitOfWork, variant_ids: Collection[UUID]
) -> dict[UUID, SaleVariant]:
    """The variants among ``variant_ids``, read inside the caller's unit of work.

    Unknown ids are missing from the result; variants of products that left the shop
    are returned, but not ``purchasable``.
    """
    ids = list(set(variant_ids))
    if not ids:
        return {}
    found = await _load(uow, variants.c.id.in_(ids))
    return {variant.variant_id: variant for variant in found}


async def load_product_variants(uow: UnitOfWork, slug: str) -> list[SaleVariant]:
    """Every variant of the product with ``slug`` (empty if there is no such product)."""
    return await _load(uow, products.c.slug == slug)


async def load_variant_by_gtin(uow: UnitOfWork, gtin: str) -> SaleVariant | None:
    """The variant whose EAN-13 is ``gtin``, if any (a scanned barcode)."""
    found = await _load(uow, variants.c.gtin == gtin)
    return found[0] if found else None


async def _load(uow: UnitOfWork, condition: ColumnElement[bool]) -> list[SaleVariant]:
    rows = (
        await uow.session.execute(
            select(
                variants.c.id,
                variants.c.sku,
                variants.c.gtin,
                variants.c.price_cents,
                variants.c.compare_at_price_cents,
                variants.c.active,
                variants.c.allow_backorder,
                variants.c.lead_time_min_weeks,
                variants.c.lead_time_max_weeks,
                variants.c.finish_code,
                variants.c.color,
                finishes.c.name.label("finish_name"),
                product_scales.c.scale_code,
                scales.c.name.label("scale_name"),
                products.c.id.label("product_id"),
                products.c.slug,
                products.c.name,
                products.c.status,
            )
            .join(finishes, finishes.c.code == variants.c.finish_code)
            .join(product_scales, product_scales.c.id == variants.c.product_scale_id)
            .join(scales, scales.c.code == product_scales.c.scale_code)
            .join(products, products.c.id == product_scales.c.product_id)
            .where(condition)
            .order_by(scales.c.ratio_denominator.desc(), finishes.c.position, variants.c.color)
        )
    ).all()
    if not rows:
        return []
    galleries: defaultdict[UUID, list[_Photo]] = defaultdict(list)
    media_rows = await uow.session.execute(
        select(
            product_media.c.product_id,
            product_media.c.position,
            product_media.c.asset_id,
            product_media.c.scale_code,
            product_media.c.finish_code,
            product_media.c.color,
        ).where(product_media.c.product_id.in_({row.product_id for row in rows}))
    )
    for media in media_rows:
        galleries[media.product_id].append(
            _Photo(media.position, media.asset_id, media.scale_code, media.finish_code, media.color)
        )
    return [
        SaleVariant(
            variant_id=row.id,
            gtin=row.gtin,
            product_id=row.product_id,
            product_slug=row.slug,
            product_name=row.name,
            scale_code=row.scale_code,
            scale_name=row.scale_name,
            finish_code=row.finish_code,
            finish_name=row.finish_name,
            color=row.color,
            sku=row.sku,
            price_cents=row.price_cents,
            compare_at_price_cents=row.compare_at_price_cents,
            image_asset_id=_best_image(
                galleries[row.product_id], row.scale_code, row.finish_code, row.color
            ),
            purchasable=row.active and row.status == ProductStatus.ACTIVE,
            allow_backorder=row.allow_backorder,
            lead_time_weeks=(
                (row.lead_time_min_weeks, row.lead_time_max_weeks)
                if row.lead_time_min_weeks is not None
                else None
            ),
        )
        for row in rows
    ]


@dataclass(frozen=True, slots=True)
class _Photo:
    position: int
    asset_id: UUID
    scale_code: str | None
    finish_code: str | None
    color: str | None


def _best_image(
    gallery: list[_Photo], scale_code: str, finish_code: str, color: str
) -> UUID | None:
    # Same order as the product page's stage: a photo of the chosen scale, finish and
    # colour first, then untagged ones, then photos of other variants; ties by position.
    def score(tag: str | None, chosen: str) -> int:
        return (
            0
            if tag is not None and tag.casefold() == chosen.casefold()
            else 1
            if tag is None
            else 2
        )

    if not gallery:
        return None
    best = min(
        gallery,
        key=lambda photo: (
            score(photo.scale_code, scale_code)
            + score(photo.finish_code, finish_code)
            + score(photo.color, color or ""),
            photo.position,
        ),
    )
    return best.asset_id
