"""Read-only facade for marketplaces: a product in one scale as an offer elsewhere shows it.

It runs SQL, so a domain layer must not import it (the pure-domain contract says so).
"""

from collections.abc import Collection
from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select

from modellbahn.modules.catalog.contracts.variants import SaleVariant, load_sale_variants
from modellbahn.modules.catalog.domain.model import ProductStatus
from modellbahn.modules.catalog.infrastructure.tables import (
    categories,
    epochs,
    product_epochs,
    product_media,
    product_scales,
    products,
    scales,
    variants,
)
from modellbahn.platform.uow import UnitOfWork

__all__ = [
    "CategoryLabel",
    "ListingSource",
    "ProductLabel",
    "load_category_labels",
    "load_listing_source",
    "load_product_labels",
    "load_variants_by_sku",
]


@dataclass(frozen=True, slots=True)
class ListingSource:
    """What an offer of the product in one scale says: texts, sizes, photos and variants."""

    product_id: UUID
    number: int
    slug: str
    name: str
    summary: str
    description: str
    prototype: str
    active: bool
    """In the shop: only then may it be offered elsewhere."""
    category_ids: tuple[UUID, ...]
    """The product's category and its parents, the most specific first."""
    epochs: tuple[str, ...]
    """``Epoche III (1949 bis 1970)``, in the order of the railway's history."""
    scale_code: str
    scale_name: str
    ratio: str
    """``1:87``, written the German way (``1:22,5``)."""
    track_gauge_mm: Decimal | None
    length_mm: Decimal | None
    width_mm: Decimal | None
    height_mm: Decimal | None
    weight_g: int | None
    variants: tuple[SaleVariant, ...]
    """The variants in this scale, in the shop's order (finish, then colour)."""
    image_ids: tuple[UUID, ...]
    """Photos for this scale (tagged with it, or untagged), in gallery order."""


@dataclass(frozen=True, slots=True)
class ProductLabel:
    product_id: UUID
    number: int
    slug: str
    name: str
    status: ProductStatus


@dataclass(frozen=True, slots=True)
class CategoryLabel:
    category_id: UUID
    path: str
    """``Straßenfahrzeuge / LKW / Feuerwehr``."""


def _ratio(denominator: Decimal) -> str:
    whole = denominator == denominator.to_integral_value()
    text = f"{int(denominator)}" if whole else f"{denominator:.1f}".replace(".", ",")
    return f"1:{text}"


async def load_listing_source(
    uow: UnitOfWork, product_id: UUID, scale_code: str
) -> ListingSource | None:
    """The product in the scale, read inside the caller's unit of work (None if either is gone)."""
    row = (
        await uow.session.execute(
            select(
                products.c.id,
                products.c.number,
                products.c.slug,
                products.c.name,
                products.c.summary,
                products.c.description,
                products.c.prototype,
                products.c.status,
                products.c.primary_category_id,
                product_scales.c.id.label("product_scale_id"),
                product_scales.c.length_mm,
                product_scales.c.width_mm,
                product_scales.c.height_mm,
                product_scales.c.weight_g,
                scales.c.name.label("scale_name"),
                scales.c.ratio_denominator,
                scales.c.track_gauge_mm,
            )
            .join(product_scales, product_scales.c.product_id == products.c.id)
            .join(scales, scales.c.code == product_scales.c.scale_code)
            .where(products.c.id == product_id, product_scales.c.scale_code == scale_code)
        )
    ).one_or_none()
    if row is None:
        return None
    variant_ids = (
        await uow.session.scalars(
            select(variants.c.id).where(variants.c.product_scale_id == row.product_scale_id)
        )
    ).all()
    sale_variants = await load_sale_variants(uow, variant_ids)
    ordered = sorted(sale_variants.values(), key=lambda v: (_finish_rank(v), v.color.casefold()))
    epoch_rows = await uow.session.execute(
        select(epochs.c.name, epochs.c.period)
        .join(product_epochs, product_epochs.c.epoch_code == epochs.c.code)
        .where(product_epochs.c.product_id == product_id)
        .order_by(epochs.c.position)
    )
    image_rows = await uow.session.execute(
        select(product_media.c.asset_id)
        .where(
            product_media.c.product_id == product_id,
            (product_media.c.scale_code == scale_code) | product_media.c.scale_code.is_(None),
        )
        .order_by(product_media.c.position)
    )
    return ListingSource(
        product_id=row.id,
        number=row.number,
        slug=row.slug,
        name=row.name,
        summary=row.summary,
        description=row.description,
        prototype=row.prototype,
        active=row.status == ProductStatus.ACTIVE,
        category_ids=await _category_chain(uow, row.primary_category_id),
        epochs=tuple(f"{epoch.name} ({epoch.period})" for epoch in epoch_rows),
        scale_code=scale_code,
        scale_name=row.scale_name,
        ratio=_ratio(row.ratio_denominator),
        track_gauge_mm=row.track_gauge_mm,
        length_mm=row.length_mm,
        width_mm=row.width_mm,
        height_mm=row.height_mm,
        weight_g=row.weight_g,
        variants=tuple(ordered),
        image_ids=tuple(image.asset_id for image in image_rows),
    )


def _finish_rank(variant: SaleVariant) -> int:
    # Kit before finished model, like the shop lists them.
    return 0 if variant.finish_code == "unpainted" else 1


async def _category_chain(uow: UnitOfWork, category_id: UUID | None) -> tuple[UUID, ...]:
    if category_id is None:
        return ()
    rows = await uow.session.execute(select(categories.c.id, categories.c.parent_id))
    parents: dict[UUID, UUID | None] = {row.id: row.parent_id for row in rows}
    chain: list[UUID] = []
    current: UUID | None = category_id
    while current is not None and current not in chain:
        chain.append(current)
        current = parents.get(current)
    return tuple(chain)


async def load_product_labels(
    uow: UnitOfWork, product_ids: Collection[UUID]
) -> dict[UUID, ProductLabel]:
    """Number, address, name and state of the products among ``product_ids``."""
    ids = list(set(product_ids))
    if not ids:
        return {}
    rows = await uow.session.execute(
        select(
            products.c.id, products.c.number, products.c.slug, products.c.name, products.c.status
        ).where(products.c.id.in_(ids))
    )
    return {
        row.id: ProductLabel(
            product_id=row.id, number=row.number, slug=row.slug, name=row.name, status=row.status
        )
        for row in rows
    }


async def load_category_labels(uow: UnitOfWork) -> list[CategoryLabel]:
    """Every category with its path, in the order of the tree."""
    rows = (
        await uow.session.execute(
            select(categories.c.id, categories.c.parent_id, categories.c.name).order_by(
                categories.c.position, categories.c.name
            )
        )
    ).all()
    children: dict[UUID | None, list[tuple[UUID, str]]] = {}
    for row in rows:
        children.setdefault(row.parent_id, []).append((row.id, row.name))
    labels: list[CategoryLabel] = []

    def walk(parent: UUID | None, prefix: str) -> None:
        for category_id, name in children.get(parent, []):
            path = f"{prefix}{name}"
            labels.append(CategoryLabel(category_id=category_id, path=path))
            walk(category_id, f"{path} / ")

    walk(None, "")
    return labels


async def load_variants_by_sku(uow: UnitOfWork, skus: Collection[str]) -> dict[str, SaleVariant]:
    """The variants with the given article numbers (unknown numbers are missing)."""
    wanted = list(set(skus))
    if not wanted:
        return {}
    ids = (await uow.session.scalars(select(variants.c.id).where(variants.c.sku.in_(wanted)))).all()
    found = await load_sale_variants(uow, ids)
    return {variant.sku: variant for variant in found.values()}
