"""SQLAlchemy implementations of the marketplace repositories and unit of work.

Repositories only read and stage changes; committing is the unit of work's job.
"""

import secrets
from collections.abc import Collection, Sequence
from datetime import datetime
from functools import partial
from uuid import UUID

from sqlalchemy import ColumnElement, Select, delete, exists, insert, select, tuple_, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from modellbahn.modules.catalog.contracts.listings import (
    CategoryLabel,
    ListingSource,
    ProductLabel,
    load_category_labels,
    load_listing_source,
    load_product_labels,
    load_variants_by_sku,
)
from modellbahn.modules.catalog.contracts.variants import SaleVariant
from modellbahn.modules.inventory.contracts.stock import load_free_units
from modellbahn.modules.marketplace.application.ports import ListingCursor
from modellbahn.modules.marketplace.domain.model import (
    EBAY,
    EbayAccount,
    Listing,
    ListingStatus,
    MarketplaceOrder,
)
from modellbahn.modules.marketplace.infrastructure.mapping import start_mappers
from modellbahn.modules.marketplace.infrastructure.tables import (
    category_map,
    ebay_account,
    listing_items,
    listings,
    marketplace_orders,
    test_sales,
)
from modellbahn.modules.media.contracts.images import RenditionFormat, load_images
from modellbahn.modules.sales.contracts.addresses import address_problem
from modellbahn.modules.sales.contracts.orders import (
    Shipment,
    load_order_numbers,
    load_shipment,
)
from modellbahn.platform.ids import new_id
from modellbahn.platform.uow import UnitOfWork

# The uncropped sizes of the gallery; eBay gets the largest one an image has.
_GALLERY_SIZES = frozenset({"sm", "md", "lg", "xl"})


def _locked[*Ts](statement: Select[*Ts], for_update: bool) -> Select[*Ts]:
    if not for_update:
        return statement
    # FOR NO KEY UPDATE: no use case changes a key, and inserting an item or an order
    # line only takes a key-share lock on the row it refers to.
    return statement.with_for_update(key_share=True).execution_options(populate_existing=True)


def _on_ebay() -> ColumnElement[bool]:
    """Listings a sync has work for: wanted ones, and those still up that are not."""
    up = (listings.c.external_id != "") & (listings.c.status != ListingStatus.ENDED)
    return listings.c.wanted | up


class SqlAccountRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, *, for_update: bool = False) -> EbayAccount | None:
        statement = _locked(select(EbayAccount).where(ebay_account.c.channel == EBAY), for_update)
        return (await self._session.execute(statement)).scalar_one_or_none()

    def add(self, account: EbayAccount) -> None:
        self._session.add(account)


class SqlCategoryMapRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def all(self) -> dict[UUID, str]:
        rows = await self._session.execute(
            select(category_map.c.category_id, category_map.c.ebay_category_id)
        )
        return {row.category_id: row.ebay_category_id for row in rows}

    async def replace(self, mapping: dict[UUID, str], now: datetime) -> None:
        await self._session.execute(delete(category_map))
        if mapping:
            await self._session.execute(
                insert(category_map),
                [
                    {"category_id": category_id, "ebay_category_id": number, "updated_at": now}
                    for category_id, number in mapping.items()
                ],
            )


class SqlListingRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, listing_id: UUID, *, for_update: bool = False) -> Listing | None:
        statement = _locked(select(Listing).where(listings.c.id == listing_id), for_update)
        return (await self._session.execute(statement)).scalar_one_or_none()

    async def find(
        self, product_id: UUID, scale_code: str, *, for_update: bool = False
    ) -> Listing | None:
        statement = _locked(
            select(Listing).where(
                listings.c.product_id == product_id, listings.c.scale_code == scale_code
            ),
            for_update,
        )
        return (await self._session.execute(statement)).scalar_one_or_none()

    async def of_product(self, product_id: UUID) -> list[Listing]:
        statement = (
            select(Listing)
            .where(listings.c.product_id == product_id)
            .order_by(listings.c.group_key)
        )
        return list((await self._session.execute(statement)).scalars())

    async def page(self, *, after: ListingCursor | None, limit: int) -> list[Listing]:
        statement = select(Listing).order_by(listings.c.updated_at.desc(), listings.c.id.desc())
        if after is not None:
            statement = statement.where(
                tuple_(listings.c.updated_at, listings.c.id) < tuple_(after.updated_at, after.id)
            )
        return list((await self._session.execute(statement.limit(limit))).scalars())

    async def due(self, limit: int) -> list[UUID]:
        statement = (
            select(listings.c.id)
            .where(listings.c.needs_sync)
            .order_by(listings.c.updated_at, listings.c.id)
            .limit(limit)
            # A listing someone syncs right now ("sync now" in the Stellwerk) is skipped.
            .with_for_update(skip_locked=True)
        )
        return list((await self._session.execute(statement)).scalars())

    async def mark_due_for_product(self, product_id: UUID, now: datetime) -> int:
        return await self._mark_due(listings.c.product_id == product_id, now)

    async def mark_due_for_variants(self, variant_ids: Collection[UUID], now: datetime) -> int:
        ids = list(set(variant_ids))
        if not ids:
            return 0
        offering = exists().where(
            listing_items.c.listing_id == listings.c.id, listing_items.c.variant_id.in_(ids)
        )
        return await self._mark_due(offering, now)

    async def mark_all_due(self, now: datetime) -> int:
        return await self._mark_due(None, now)

    async def up(self) -> list[Listing]:
        statement = (
            select(Listing)
            .where(listings.c.external_id != "", listings.c.status != ListingStatus.ENDED)
            .order_by(listings.c.group_key)
        )
        return list((await self._session.execute(statement)).scalars())

    async def _mark_due(self, condition: ColumnElement[bool] | None, now: datetime) -> int:
        statement = (
            update(listings)
            .where(_on_ebay())
            .values(needs_sync=True, updated_at=now)
            .execution_options(synchronize_session=False)
        )
        if condition is not None:
            statement = statement.where(condition)
        result = await self._session.execute(statement)
        return int(result.rowcount)  # type: ignore[attr-defined]

    async def item_for_sku(self, sku: str) -> tuple[Listing, int] | None:
        row = (
            await self._session.execute(
                select(Listing, listing_items.c.price_cents)
                .join(listing_items, listing_items.c.listing_id == listings.c.id)
                .where(
                    listing_items.c.sku == sku,
                    listings.c.external_id != "",
                    listings.c.status != ListingStatus.ENDED,
                )
            )
        ).one_or_none()
        if row is None:
            return None
        return row[0], int(row[1])

    def add(self, listing: Listing) -> None:
        self._session.add(listing)


class SqlMarketplaceOrderRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(
        self, marketplace_order_id: UUID, *, for_update: bool = False
    ) -> MarketplaceOrder | None:
        statement = _locked(
            select(MarketplaceOrder).where(marketplace_orders.c.id == marketplace_order_id),
            for_update,
        )
        return (await self._session.execute(statement)).scalar_one_or_none()

    async def by_external(
        self, channel: str, external_id: str, *, for_update: bool = False
    ) -> MarketplaceOrder | None:
        statement = _locked(
            select(MarketplaceOrder).where(
                marketplace_orders.c.channel == channel,
                marketplace_orders.c.external_id == external_id,
            ),
            for_update,
        )
        return (await self._session.execute(statement)).scalar_one_or_none()

    async def by_order_id(
        self, order_id: UUID, *, for_update: bool = False
    ) -> MarketplaceOrder | None:
        statement = _locked(
            select(MarketplaceOrder).where(marketplace_orders.c.order_id == order_id), for_update
        )
        return (await self._session.execute(statement)).scalar_one_or_none()

    async def recent(self, limit: int) -> list[MarketplaceOrder]:
        statement = (
            select(MarketplaceOrder)
            .order_by(marketplace_orders.c.received_at.desc(), marketplace_orders.c.id.desc())
            .limit(limit)
        )
        return list((await self._session.execute(statement)).scalars())

    def add(self, order: MarketplaceOrder) -> None:
        self._session.add(order)


class SqlTestMarketplace:
    """Sales on the built-in test marketplace; the test gateway reports them as orders."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def sell(
        self, *, sku: str, quantity: int, unit_price_cents: int, shipping_cents: int, now: datetime
    ) -> str:
        # Shaped like eBay's order numbers, with a T for test: T7-04213-88351.
        external_id = (
            f"T{secrets.randbelow(10)}-{secrets.randbelow(100_000):05d}"
            f"-{secrets.randbelow(100_000):05d}"
        )
        await self._session.execute(
            insert(test_sales).values(
                id=new_id(),
                external_id=external_id,
                sku=sku,
                quantity=quantity,
                unit_price_cents=unit_price_cents,
                shipping_cents=shipping_cents,
                created_at=now,
                modified_at=now,
            )
        )
        return external_id

    async def cancel(self, external_id: str, now: datetime) -> bool:
        result = await self._session.execute(
            update(test_sales)
            .where(test_sales.c.external_id == external_id, test_sales.c.cancelled_at.is_(None))
            .values(cancelled_at=now, modified_at=now)
        )
        return bool(result.rowcount)  # type: ignore[attr-defined]


class SqlCatalog:
    """The catalogue's listing facade, inside this unit of work's transaction."""

    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    async def listing_source(self, product_id: UUID, scale_code: str) -> ListingSource | None:
        return await load_listing_source(self._uow, product_id, scale_code)

    async def variants_by_sku(self, skus: Collection[str]) -> dict[str, SaleVariant]:
        return await load_variants_by_sku(self._uow, skus)

    async def product_labels(self, product_ids: Collection[UUID]) -> dict[UUID, ProductLabel]:
        return await load_product_labels(self._uow, product_ids)

    async def categories(self) -> list[CategoryLabel]:
        return await load_category_labels(self._uow)


class SqlInventory:
    """The inventory module's stock facade, inside this unit of work's transaction."""

    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    async def free_units(self, variant_ids: Collection[UUID]) -> dict[UUID, int]:
        return await load_free_units(self._uow, variant_ids)


class SqlImages:
    """The media module's image facade, with URLs eBay can fetch from outside."""

    def __init__(self, uow: UnitOfWork, image_base_url: str) -> None:
        self._uow = uow
        self._image_base_url = image_base_url

    async def public_urls(self, asset_ids: Sequence[UUID]) -> dict[UUID, str]:
        images = await load_images(self._uow, asset_ids, public_base_url=self._image_base_url)
        urls: dict[UUID, str] = {}
        for asset_id in dict.fromkeys(asset_ids):
            image = images.get(asset_id)
            if image is None or not image.is_ready:
                continue
            sizes = [
                rendition
                for rendition in image.renditions
                if rendition.name in _GALLERY_SIZES and rendition.format is RenditionFormat.WEBP
            ]
            if sizes:
                urls[asset_id] = max(sizes, key=lambda rendition: rendition.width).url
        return urls


class SqlSales:
    """The sales module's order facade, inside this unit of work's transaction."""

    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    async def shipment(self, order_id: UUID) -> Shipment | None:
        return await load_shipment(self._uow, order_id)

    async def order_numbers(self, order_ids: Collection[UUID]) -> dict[UUID, str]:
        return await load_order_numbers(self._uow, order_ids)

    def address_problem(
        self, *, recipient: str, street: str, postal_code: str, city: str, country_code: str
    ) -> str | None:
        return address_problem(
            recipient=recipient,
            street=street,
            postal_code=postal_code,
            city=city,
            country_code=country_code,
        )


class SqlMarketplaceUnitOfWork(UnitOfWork):
    """Unit of work with the marketplace repositories attached."""

    account: SqlAccountRepository
    categories: SqlCategoryMapRepository
    listings: SqlListingRepository
    orders: SqlMarketplaceOrderRepository
    test_marketplace: SqlTestMarketplace
    catalog: SqlCatalog
    inventory: SqlInventory
    images: SqlImages
    sales: SqlSales

    def __init__(
        self, session_factory: async_sessionmaker[AsyncSession], *, image_base_url: str
    ) -> None:
        super().__init__(session_factory)
        self._image_base_url = image_base_url

    def _attach(self, session: AsyncSession) -> None:
        start_mappers()
        self.account = SqlAccountRepository(session)
        self.categories = SqlCategoryMapRepository(session)
        self.listings = SqlListingRepository(session)
        self.orders = SqlMarketplaceOrderRepository(session)
        self.test_marketplace = SqlTestMarketplace(session)
        self.catalog = SqlCatalog(self)
        self.inventory = SqlInventory(self)
        self.images = SqlImages(self, self._image_base_url)
        self.sales = SqlSales(self)


def image_base_url(*, public_base_url: str, media_public_base_url: str) -> str:
    """Where eBay fetches the photos: the media prefix, made absolute with the site's URL."""
    if media_public_base_url.startswith(("http://", "https://")):
        return media_public_base_url
    return f"{public_base_url}{media_public_base_url}"


def marketplace_uow_factory(
    session_factory: async_sessionmaker[AsyncSession], *, image_base_url: str
) -> partial[SqlMarketplaceUnitOfWork]:
    """The factory the marketplace services get: a fresh unit of work per call."""
    return partial(SqlMarketplaceUnitOfWork, session_factory, image_base_url=image_base_url)
