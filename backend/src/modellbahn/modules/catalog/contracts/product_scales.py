"""Read-only facade for manufacturing: the scales, and a product in one scale with its parts.

It runs SQL, so a domain layer must not import it (the pure-domain contract says so).
"""

from collections.abc import Collection
from dataclasses import dataclass
from typing import Final
from uuid import UUID

from sqlalchemy import select

from modellbahn.modules.catalog.domain.model import ProductStatus
from modellbahn.modules.catalog.infrastructure.tables import product_scales, products, scales
from modellbahn.platform.uow import UnitOfWork

__all__ = [
    "PRODUCT_SCALE_REFERENCE",
    "SCALE_REFERENCE",
    "ProductScaleLabel",
    "load_product_scale_labels",
    "load_scale_names",
]

SCALE_REFERENCE: Final = "catalog.scales.code"
"""Target for another module's foreign key to a scale (``RESTRICT``: a scale with parts
stays). Importing it also puts the catalogue tables on the shared metadata."""

PRODUCT_SCALE_REFERENCE: Final = (
    "catalog.product_scales.id",
    "catalog.product_scales.scale_code",
)
"""Target for a composite foreign key ``(product_scale_id, scale_code)`` (``RESTRICT``):
the database then knows the scale of the product, and the catalogue cannot drop a scale
from a product while a bill of materials belongs to it."""


@dataclass(frozen=True, slots=True)
class ProductScaleLabel:
    """``Stellwerk Altenau · H0``: a product in one scale, as lists name it."""

    product_scale_id: UUID
    product_id: UUID
    product_number: int
    product_name: str
    product_status: ProductStatus
    scale_code: str
    scale_name: str


async def load_product_scale_labels(
    uow: UnitOfWork, product_scale_ids: Collection[UUID]
) -> dict[UUID, ProductScaleLabel]:
    """The products in their scales among ``product_scale_ids``; unknown ids are left out."""
    ids = list(set(product_scale_ids))
    if not ids:
        return {}
    rows = await uow.session.execute(
        select(
            product_scales.c.id,
            product_scales.c.scale_code,
            products.c.id.label("product_id"),
            products.c.number,
            products.c.name,
            products.c.status,
            scales.c.name.label("scale_name"),
        )
        .join(products, products.c.id == product_scales.c.product_id)
        .join(scales, scales.c.code == product_scales.c.scale_code)
        .where(product_scales.c.id.in_(ids))
    )
    return {
        row.id: ProductScaleLabel(
            product_scale_id=row.id,
            product_id=row.product_id,
            product_number=row.number,
            product_name=row.name,
            product_status=ProductStatus(row.status),
            scale_code=row.scale_code,
            scale_name=row.scale_name,
        )
        for row in rows
    }


async def load_scale_names(uow: UnitOfWork) -> dict[str, str]:
    """Every scale's display name by code (``1:24`` for code ``124``), largest first."""
    rows = await uow.session.execute(
        select(scales.c.code, scales.c.name).order_by(scales.c.ratio_denominator)
    )
    return {row.code: row.name for row in rows}
