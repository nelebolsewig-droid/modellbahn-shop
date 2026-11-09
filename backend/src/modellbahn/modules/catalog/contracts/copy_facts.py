"""Read-only facade for product texts: the facts a writer (person or model) may rely on.

It runs SQL, so a domain layer must not import it (the pure-domain contract says so).
Prices are left out on purpose: the shop shows them next to the text, and a text that
names a price is wrong the day the price changes.
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import Final
from uuid import UUID

from sqlalchemy import select

from modellbahn.modules.catalog.domain.model import ProductStatus
from modellbahn.modules.catalog.infrastructure.tables import (
    categories,
    epochs,
    finishes,
    product_epochs,
    product_media,
    product_scales,
    products,
    scales,
    variants,
)
from modellbahn.platform.uow import UnitOfWork

__all__ = [
    "PRODUCT_REFERENCE",
    "CopyScale",
    "CopySource",
    "load_copy_source",
    "load_draft_products",
]

PRODUCT_REFERENCE: Final = "catalog.products.id"
"""Foreign key target for rows of other modules that belong to a product."""


@dataclass(frozen=True, slots=True)
class CopyScale:
    code: str
    name: str
    ratio: str
    """``1:87``, written the German way (``1:22,5``)."""
    track_gauge_mm: Decimal | None
    length_mm: Decimal | None
    width_mm: Decimal | None
    height_mm: Decimal | None
    weight_g: int | None
    finishes: tuple[str, ...]
    """Names of the active finishes in this scale (``Bausatz``, ``Fertigmodell``)."""
    colors: tuple[str, ...]
    """Colours of the active finished models in this scale."""


@dataclass(frozen=True, slots=True)
class CopySource:
    product_id: UUID
    name: str
    status: ProductStatus
    summary: str
    description: str
    prototype: str
    category_path: str
    """``Straßenfahrzeuge / LKW / Feuerwehr``, empty without a category."""
    epochs: tuple[str, ...]
    """``Epoche III (1949 bis 1970)``, in the order of the railway's history."""
    scales: tuple[CopyScale, ...]
    image_ids: tuple[UUID, ...]
    """The gallery in order: the main photo first."""


def _ratio(denominator: Decimal) -> str:
    whole = denominator == denominator.to_integral_value()
    text = f"{int(denominator)}" if whole else f"{denominator:.1f}".replace(".", ",")
    return f"1:{text}"


async def load_copy_source(uow: UnitOfWork, product_id: UUID) -> CopySource | None:
    """The product's facts, read inside the caller's unit of work (None if it is gone)."""
    session = uow.session
    row = (
        await session.execute(
            select(
                products.c.id,
                products.c.name,
                products.c.status,
                products.c.summary,
                products.c.description,
                products.c.prototype,
                products.c.primary_category_id,
            ).where(products.c.id == product_id)
        )
    ).one_or_none()
    if row is None:
        return None
    scale_rows = (
        await session.execute(
            select(
                product_scales.c.id,
                product_scales.c.scale_code,
                product_scales.c.length_mm,
                product_scales.c.width_mm,
                product_scales.c.height_mm,
                product_scales.c.weight_g,
                scales.c.name,
                scales.c.ratio_denominator,
                scales.c.track_gauge_mm,
            )
            .join(scales, scales.c.code == product_scales.c.scale_code)
            .where(product_scales.c.product_id == product_id)
            .order_by(scales.c.ratio_denominator.desc())
        )
    ).all()
    variant_rows = (
        await session.execute(
            select(
                variants.c.product_scale_id,
                variants.c.color,
                finishes.c.name,
                finishes.c.position,
            )
            .join(finishes, finishes.c.code == variants.c.finish_code)
            .where(
                variants.c.product_scale_id.in_([s.id for s in scale_rows]),
                variants.c.active,
            )
            .order_by(finishes.c.position, variants.c.color)
        )
    ).all()
    epoch_rows = await session.execute(
        select(epochs.c.name, epochs.c.period)
        .join(product_epochs, product_epochs.c.epoch_code == epochs.c.code)
        .where(product_epochs.c.product_id == product_id)
        .order_by(epochs.c.position)
    )
    image_rows = await session.execute(
        select(product_media.c.asset_id)
        .where(product_media.c.product_id == product_id)
        .order_by(product_media.c.position)
    )
    return CopySource(
        product_id=row.id,
        name=row.name,
        status=row.status,
        summary=row.summary,
        description=row.description,
        prototype=row.prototype,
        category_path=await _category_path(uow, row.primary_category_id),
        epochs=tuple(f"{epoch.name} ({epoch.period})" for epoch in epoch_rows),
        scales=tuple(
            CopyScale(
                code=s.scale_code,
                name=s.name,
                ratio=_ratio(s.ratio_denominator),
                track_gauge_mm=s.track_gauge_mm,
                length_mm=s.length_mm,
                width_mm=s.width_mm,
                height_mm=s.height_mm,
                weight_g=s.weight_g,
                finishes=tuple(
                    dict.fromkeys(v.name for v in variant_rows if v.product_scale_id == s.id)
                ),
                colors=tuple(
                    dict.fromkeys(
                        v.color for v in variant_rows if v.product_scale_id == s.id and v.color
                    )
                ),
            )
            for s in scale_rows
        ),
        image_ids=tuple(image.asset_id for image in image_rows),
    )


async def load_draft_products(uow: UnitOfWork) -> list[tuple[UUID, str]]:
    """Id and name of every product still in draft, the oldest first."""
    rows = await uow.session.execute(
        select(products.c.id, products.c.name)
        .where(products.c.status == ProductStatus.DRAFT)
        .order_by(products.c.created_at, products.c.number)
    )
    return [(row.id, row.name) for row in rows]


async def _category_path(uow: UnitOfWork, category_id: UUID | None) -> str:
    if category_id is None:
        return ""
    rows = await uow.session.execute(
        select(categories.c.id, categories.c.parent_id, categories.c.name)
    )
    nodes = {row.id: (row.parent_id, row.name) for row in rows}
    names: list[str] = []
    current: UUID | None = category_id
    while current is not None and current in nodes and len(names) < len(nodes):
        parent, name = nodes[current]
        names.append(name)
        current = parent
    return " / ".join(reversed(names))
