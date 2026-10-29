"""Imperative mapping of the marketplace's domain classes onto their tables.

Listing items belong to their listing and order lines to their order; they are loaded
with their root (``selectin``: the async session cannot load lazily).
"""

from sqlalchemy import inspect
from sqlalchemy.orm import relationship

from modellbahn.modules.marketplace.domain.model import (
    EbayAccount,
    Listing,
    ListingItem,
    MarketplaceOrder,
    MarketplaceOrderLine,
)
from modellbahn.modules.marketplace.infrastructure import tables
from modellbahn.platform.db import mapper_registry


def start_mappers() -> None:
    """Map the marketplace classes. Safe to call more than once."""
    if inspect(Listing, raiseerr=False) is not None:
        return
    mapper_registry.map_imperatively(EbayAccount, tables.ebay_account)
    mapper_registry.map_imperatively(ListingItem, tables.listing_items)
    mapper_registry.map_imperatively(
        Listing,
        tables.listings,
        properties={
            "items": relationship(
                ListingItem,
                cascade="all, delete-orphan",
                passive_deletes=True,
                lazy="selectin",
                order_by=tables.listing_items.c.sku,
            )
        },
    )
    mapper_registry.map_imperatively(MarketplaceOrderLine, tables.marketplace_order_lines)
    mapper_registry.map_imperatively(
        MarketplaceOrder,
        tables.marketplace_orders,
        properties={
            "lines": relationship(
                MarketplaceOrderLine,
                cascade="all, delete-orphan",
                passive_deletes=True,
                lazy="selectin",
                order_by=tables.marketplace_order_lines.c.position,
            )
        },
    )
