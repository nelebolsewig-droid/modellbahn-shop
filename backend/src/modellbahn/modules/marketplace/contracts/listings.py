"""Facade for the catalogue: a product's eBay listings, when the product is deleted.

It runs SQL, so a domain layer must not import it (the pure-domain contract says so).
"""

from uuid import UUID

from sqlalchemy import ColumnElement, delete, func, select

from modellbahn.modules.marketplace.domain.model import ListingStatus
from modellbahn.modules.marketplace.infrastructure.tables import listings
from modellbahn.platform.uow import UnitOfWork

__all__ = ["count_live_listings", "remove_listings"]


def _up() -> ColumnElement[bool]:
    """eBay shows it (``Listing.is_up``): it went up and was not ended since.

    A listing the shop holds back (e.g. its product left the shop) has no eBay id any more.
    """
    return (listings.c.external_id != "") & (listings.c.status != ListingStatus.ENDED)


async def count_live_listings(uow: UnitOfWork, product_id: UUID) -> int:
    """Listings of the product that eBay still shows."""
    count = (
        await uow.session.execute(
            select(func.count()).where(listings.c.product_id == product_id, _up())
        )
    ).scalar_one()
    return int(count)


async def remove_listings(uow: UnitOfWork, product_id: UUID) -> int:
    """Delete the product's listings that eBay no longer shows (their items go along)."""
    result = await uow.session.execute(
        delete(listings).where(listings.c.product_id == product_id, ~_up())
    )
    return int(result.rowcount or 0)  # type: ignore[attr-defined]
