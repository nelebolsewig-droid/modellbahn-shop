"""Imperative mapping of the media domain classes onto their tables.

Image details and renditions belong to the asset aggregate and are loaded with it
(``selectin``: the async session cannot load lazily).
"""

from sqlalchemy import inspect
from sqlalchemy.orm import relationship

from modellbahn.modules.media.domain.model import Asset, ImageDetails, Rendition
from modellbahn.modules.media.infrastructure import tables
from modellbahn.platform.db import mapper_registry


def start_mappers() -> None:
    """Map the media classes. Safe to call more than once."""
    if inspect(Asset, raiseerr=False) is not None:
        return
    mapper_registry.map_imperatively(
        ImageDetails,
        tables.image_details,
        # The column only exists for the foreign key on (id, kind); the database fills it.
        exclude_properties=["asset_kind"],
    )
    mapper_registry.map_imperatively(Rendition, tables.renditions)
    mapper_registry.map_imperatively(
        Asset,
        tables.assets,
        # Concurrent writers of the same asset fail instead of overwriting each other.
        version_id_col=tables.assets.c.version,
        properties={
            "image": relationship(
                ImageDetails,
                primaryjoin=tables.assets.c.id == tables.image_details.c.asset_id,
                foreign_keys=[tables.image_details.c.asset_id],
                uselist=False,
                cascade="all, delete-orphan",
                passive_deletes=True,
                lazy="selectin",
            ),
            "renditions": relationship(
                Rendition,
                cascade="all, delete-orphan",
                passive_deletes=True,
                lazy="selectin",
                order_by=[tables.renditions.c.width, tables.renditions.c.format],
            ),
        },
    )
