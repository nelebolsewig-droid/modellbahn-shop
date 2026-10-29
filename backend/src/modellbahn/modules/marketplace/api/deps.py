"""FastAPI dependencies of the marketplace API: the services and who may do what."""

from typing import Annotated

from fastapi import Depends, Request

from modellbahn.modules.identity.contracts.auth import StaffMember, StaffRole, require_staff
from modellbahn.modules.marketplace.application.marketplace import Marketplace
from modellbahn.platform.errors import ConflictError

MARKETPLACE_STATE = "marketplace"
"""Name on ``app.state`` of the :class:`Marketplace` (None with ``MB_EBAY_MODE=off``)."""


def get_optional_marketplace(request: Request) -> Marketplace | None:
    marketplace: object = getattr(request.app.state, MARKETPLACE_STATE, None)
    return marketplace if isinstance(marketplace, Marketplace) else None


def get_marketplace(
    marketplace: Annotated[Marketplace | None, Depends(get_optional_marketplace)],
) -> Marketplace:
    if marketplace is None:
        raise ConflictError("eBay is switched off (MB_EBAY_MODE=off).", code="ebay_off")
    return marketplace


OptionalMarketplaceDep = Annotated[Marketplace | None, Depends(get_optional_marketplace)]
MarketplaceDep = Annotated[Marketplace, Depends(get_marketplace)]

# The connection opens the shop's seller account: only the owner connects and configures it.
EbayOwner = Annotated[StaffMember, Depends(require_staff(StaffRole.OWNER))]
# Offering products there is catalogue work, like the shop's own pages.
ListingEditor = Annotated[StaffMember, Depends(require_staff(StaffRole.OWNER, StaffRole.STAFF))]
