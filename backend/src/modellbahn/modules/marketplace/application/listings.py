"""Use cases of the offers on eBay: which products go up, and keeping them in step.

The shop is the master: whenever a product, its stock or the account's settings change,
its listings are due, and a sync rewrites them on eBay as a whole (the worker every
minute, or "sync now" in the Stellwerk). A listing the shop cannot show as it is (no
photo, no category, not in the shop) comes down with the reason; one with nothing to
sell pauses until stock comes back.
"""

import base64
import binascii
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Final
from uuid import UUID

import structlog

from modellbahn.modules.catalog.contracts.listings import ListingSource, ProductLabel
from modellbahn.modules.marketplace.application.access import EbayAccess
from modellbahn.modules.marketplace.application.drafts import (
    HeldBack,
    build_draft,
    ebay_category,
    group_key,
)
from modellbahn.modules.marketplace.application.ports import (
    AccessTokenRejectedError,
    EbayGateway,
    ListingCursor,
    ListingDraft,
    MarketplaceRejectedError,
    MarketplaceUnavailableError,
    MarketplaceUnitOfWork,
    UnitOfWorkFactory,
)
from modellbahn.modules.marketplace.domain.errors import (
    AccountNotReadyError,
    InvalidFieldError,
    ListingNotFoundError,
    NotConnectedError,
)
from modellbahn.modules.marketplace.domain.events import ListingChanged
from modellbahn.modules.marketplace.domain.model import EbayAccount, Listing, ListingItem
from modellbahn.platform.clock import Clock
from modellbahn.platform.uow import UniqueViolationError

_logger = structlog.get_logger(__name__)

SYNC_BATCH_SIZE: Final = 25


@dataclass(frozen=True, slots=True)
class ListingView:
    listing: Listing
    product: ProductLabel | None
    """None once the product is deleted (the next sync ends the listing)."""


@dataclass(frozen=True, slots=True)
class ListingPage:
    items: list[ListingView]
    next_cursor: str | None


def encode_cursor(cursor: ListingCursor) -> str:
    raw = json.dumps({"t": cursor.updated_at.isoformat(), "id": str(cursor.id)})
    return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")


def decode_cursor(text: str) -> ListingCursor:
    try:
        raw = json.loads(base64.urlsafe_b64decode(text + "=" * (-len(text) % 4)))
        return ListingCursor(updated_at=datetime.fromisoformat(raw["t"]), id=UUID(raw["id"]))
    except (binascii.Error, ValueError, KeyError, TypeError) as exc:
        raise InvalidFieldError("cursor", "invalid", "not a cursor of this list") from exc


class ListingService:
    def __init__(
        self,
        *,
        uow_factory: UnitOfWorkFactory,
        gateway: EbayGateway,
        access: EbayAccess,
        clock: Clock,
        brand: str,
    ) -> None:
        self._uow = uow_factory
        self._gateway = gateway
        self._access = access
        self._clock = clock
        self._brand = brand

    async def of_product(self, product_id: UUID) -> list[Listing]:
        async with self._uow() as uow:
            return await uow.listings.of_product(product_id)

    async def page(self, *, cursor: str | None, limit: int) -> ListingPage:
        after = decode_cursor(cursor) if cursor else None
        async with self._uow() as uow:
            found = await uow.listings.page(after=after, limit=limit + 1)
            labels = await uow.catalog.product_labels([item.product_id for item in found])
        items = found[:limit]
        next_cursor = None
        if len(found) > limit:
            last = items[-1]
            next_cursor = encode_cursor(ListingCursor(updated_at=last.updated_at, id=last.id))
        return ListingPage(
            items=[
                ListingView(listing=item, product=labels.get(item.product_id)) for item in items
            ],
            next_cursor=next_cursor,
        )

    async def want(self, product_id: UUID, scale_code: str, *, wanted: bool) -> Listing:
        """Offer the product in the scale on eBay, or take it down; the next sync does it."""
        try:
            return await self._want(product_id, scale_code, wanted=wanted)
        except UniqueViolationError as exc:
            # A second click created it at the same moment: now it exists, so change it.
            if exc.constraint != "uq_listings_product_id_scale_code":
                raise
            return await self._want(product_id, scale_code, wanted=wanted)

    async def _want(self, product_id: UUID, scale_code: str, *, wanted: bool) -> Listing:
        now = self._clock.now()
        async with self._uow() as uow:
            listing = await uow.listings.find(product_id, scale_code, for_update=True)
            if listing is None:
                if not wanted:
                    raise ListingNotFoundError
                source = await uow.catalog.listing_source(product_id, scale_code)
                if source is None:
                    raise ListingNotFoundError
                listing = Listing.create(
                    product_id=product_id,
                    scale_code=scale_code,
                    group_key=group_key(source.number, scale_code),
                    now=now,
                )
                uow.listings.add(listing)
            else:
                listing.want(wanted, now)
            await uow.commit()
            return listing

    async def sync_due(self) -> int:
        """Sync the listings that are due (a periodic job); how many were synced."""
        async with self._uow() as uow:
            account = await uow.account.get()
            if account is None or account.blockers:
                return 0
        async with self._uow() as uow:
            due = await uow.listings.due(SYNC_BATCH_SIZE)
        synced = 0
        for listing_id in due:
            try:
                await self.sync(listing_id)
            except MarketplaceUnavailableError as exc:
                # eBay is away or busy: the rest stays due for the next run.
                _logger.warning("marketplace.ebay.sync_postponed", reason=str(exc))
                break
            except ListingNotFoundError:
                continue
            synced += 1
        return synced

    async def sync(self, listing_id: UUID) -> Listing:
        """Rewrite the listing on eBay as the shop has it now (or end it)."""
        token = await self._access.token()
        async with self._uow() as uow:
            listing = await uow.listings.get(listing_id, for_update=True)
            if listing is None:
                raise ListingNotFoundError
            account = await uow.account.get()
            if account is None or not account.is_connected:
                raise NotConnectedError
            if account.blockers:
                raise AccountNotReadyError([blocker.value for blocker in account.blockers])
            try:
                event = await self._apply(uow, token, account, listing)
            except AccessTokenRejectedError:
                await self._access.rejected()
                raise
            except MarketplaceRejectedError as exc:
                event = listing.failed(code=exc.code, message=exc.message, now=self._clock.now())
            uow.publish(event)
            await uow.commit()
        _logger.info(
            "marketplace.listing.synced",
            group_key=listing.group_key,
            status=listing.status.value,
            error=listing.error_code,
        )
        return listing

    async def _apply(
        self, uow: MarketplaceUnitOfWork, token: str, account: EbayAccount, listing: Listing
    ) -> ListingChanged:
        now = self._clock.now()
        source = await uow.catalog.listing_source(listing.product_id, listing.scale_code)
        if not listing.wanted or source is None:
            await self._take_down(token, listing)
            if listing.wanted:
                return listing.held_back(
                    code="product_missing",
                    message="Das Produkt gibt es in diesem Maßstab nicht mehr.",
                    now=now,
                )
            return listing.ended(now)
        draft = await self._draft(uow, account, listing, source)
        if isinstance(draft, HeldBack):
            await self._take_down(token, listing)
            return listing.held_back(code=draft.code, message=draft.message, now=now)
        if not any(offer.quantity for offer in draft.offers):
            # Sold out and nothing made to order: off eBay until stock comes back.
            await self._take_down(token, listing)
            return listing.ended(now, items=_items(listing, draft, {}, source))
        published = await self._gateway.publish(token, draft)
        return listing.synced(
            external_id=published.external_id,
            items=_items(listing, draft, published.offer_ids, source),
            now=now,
        )

    async def _take_down(self, token: str, listing: Listing) -> None:
        if listing.is_up:
            await self._gateway.end(token, group_key=listing.group_key, offer_ids=listing.offer_ids)

    async def _draft(
        self,
        uow: MarketplaceUnitOfWork,
        account: EbayAccount,
        listing: Listing,
        source: ListingSource,
    ) -> ListingDraft | HeldBack:
        category_id = ebay_category(source, await uow.categories.all())
        free_units = await uow.inventory.free_units([v.variant_id for v in source.variants])
        variant_images = {
            variant.variant_id: variant.image_asset_id
            for variant in source.variants
            if variant.image_asset_id is not None
        }
        urls = await uow.images.public_urls([*source.image_ids, *variant_images.values()])
        return build_draft(
            source=source,
            listing=listing,
            account=account,
            category_id=category_id,
            free_units=free_units,
            gallery_urls=[urls[asset] for asset in source.image_ids if asset in urls],
            variant_urls={
                variant_id: urls[asset]
                for variant_id, asset in variant_images.items()
                if asset in urls
            },
            brand=self._brand,
        )


def _items(
    listing: Listing, draft: ListingDraft, offer_ids: dict[str, str], source: ListingSource
) -> list[ListingItem]:
    variant_ids = {variant.sku: variant.variant_id for variant in source.variants}
    known = listing.offer_ids
    return [
        ListingItem(
            listing_id=listing.id,
            sku=offer.sku,
            variant_id=variant_ids[offer.sku],
            offer_id=offer_ids.get(offer.sku) or known.get(offer.sku, ""),
            quantity=offer.quantity,
            price_cents=offer.price_cents,
        )
        for offer in draft.offers
    ]
