"""Imperative mapping of the catalogue domain classes onto their tables.

Gauges, variants, epochs and gallery entries belong to the product aggregate and are
loaded with it (``selectin``: the async session cannot load lazily). Categories are
an aggregate of their own; the product refers to its category by id only.
"""

from sqlalchemy import inspect
from sqlalchemy.orm import relationship

from modellbahn.modules.catalog.domain.model import (
    Category,
    Product,
    ProductEpoch,
    ProductMedia,
    ProductScale,
    Variant,
)
from modellbahn.modules.catalog.infrastructure import tables
from modellbahn.platform.db import mapper_registry


def start_mappers() -> None:
    """Map the catalogue classes. Safe to call more than once."""
    if inspect(Product, raiseerr=False) is not None:
        return
    mapper_registry.map_imperatively(Category, tables.categories)
    mapper_registry.map_imperatively(Variant, tables.variants)
    mapper_registry.map_imperatively(
        ProductScale,
        tables.product_scales,
        properties={
            "variants": relationship(
                Variant,
                cascade="all, delete-orphan",
                passive_deletes=True,
                lazy="selectin",
                order_by=tables.variants.c.created_at,
            )
        },
    )
    mapper_registry.map_imperatively(ProductEpoch, tables.product_epochs)
    mapper_registry.map_imperatively(
        ProductMedia,
        tables.product_media,
        # The column only exists for the foreign key on (id, kind); the database fills it.
        exclude_properties=["asset_kind"],
    )
    mapper_registry.map_imperatively(
        Product,
        tables.products,
        # Every change to the aggregate touches the product row, so this version
        # covers gauges, variants and the gallery too.
        version_id_col=tables.products.c.version,
        # Computed by the database; never written by the application.
        exclude_properties=["search_vector"],
        properties={
            "scales": relationship(
                ProductScale,
                cascade="all, delete-orphan",
                passive_deletes=True,
                lazy="selectin",
                order_by=tables.product_scales.c.scale_code,
            ),
            "epochs": relationship(
                ProductEpoch,
                cascade="all, delete-orphan",
                passive_deletes=True,
                lazy="selectin",
            ),
            "media": relationship(
                ProductMedia,
                cascade="all, delete-orphan",
                passive_deletes=True,
                lazy="selectin",
                order_by=tables.product_media.c.position,
            ),
        },
    )
