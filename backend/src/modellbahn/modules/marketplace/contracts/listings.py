"""Facade for the catalogue: a product's eBay listings, when the product is deleted.

It runs SQL, so a domain layer must not import it (the pure-domain contract says so).
"""

from uuid import UUID

from sqlalchemy import delete, func, select

from modellbahn.modules.marketplace.domain.model import ListingStatus
from modellbahn.modules.marketplace.infrastructure.tables import listings
from modellbahn.platform.uow import UnitOfWork

__all__ = ["count_live_listings", "remove_ended_listings"]


async def count_live_listings(uow: UnitOfWork, product_id: UUID) -> int:
    """Listings of the product that are (or may still be) up on eBay."""
    count = (
        await uow.session.execute(
            select(func.count()).where(
                listings.c.product_id == product_id, listings.c.status != ListingStatus.ENDED
            )
        )
    ).scalar_one()
    return int(count)


async def remove_ended_listings(uow: UnitOfWork, product_id: UUID) -> int:
    """Delete the product's ended listings (their items go along)."""
    result = await uow.session.execute(
        delete(listings).where(
            listings.c.product_id == product_id, listings.c.status == ListingStatus.ENDED
        )
    )
    return int(result.rowcount or 0)  # type: ignore[attr-defined]
