"""SQLAlchemy implementations of the catalogue repositories and unit of work.

Repositories only read and stage changes; committing is the unit of work's job.
"""

from collections.abc import Collection
from functools import partial
from typing import Any
from uuid import UUID

from sqlalchemy import ColumnElement, Select, exists, func, literal, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm.attributes import flag_modified

from modellbahn.modules.catalog.application.ports import (
    Article,
    ProductCursor,
    ProductOrder,
    ProductQuery,
)
from modellbahn.modules.catalog.domain.model import (
    Category,
    Epoch,
    Finish,
    Product,
    ProductStatus,
    Scale,
)
from modellbahn.modules.catalog.infrastructure.mapping import start_mappers
from modellbahn.modules.catalog.infrastructure.tables import (
    categories,
    epochs,
    finishes,
    gtin_serial_seq,
    product_epochs,
    product_media,
    product_number_seq,
    product_scales,
    products,
    scales,
    variants,
)
from modellbahn.modules.media.contracts.images import ImageView, load_images
from modellbahn.platform.uow import UnitOfWork


def _locked[*Ts](statement: Select[*Ts], for_update: bool) -> Select[*Ts]:
    if not for_update:
        return statement
    # FOR NO KEY UPDATE: no use case changes a primary key, and it does not wait for
    # the key-share locks that inserting a scale or gallery entry takes on the product.
    return statement.with_for_update(key_share=True).execution_options(populate_existing=True)


class SqlProductRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, product_id: UUID, *, for_update: bool = False) -> Product | None:
        statement = _locked(select(Product).where(products.c.id == product_id), for_update)
        return (await self._session.execute(statement)).scalar_one_or_none()

    async def get_by_slug(self, slug: str) -> Product | None:
        statement = select(Product).where(products.c.slug == slug)
        return (await self._session.execute(statement)).scalar_one_or_none()

    async def get_for_scale(
        self, product_scale_id: UUID, *, for_update: bool = False
    ) -> Product | None:
        owner = select(product_scales.c.product_id).where(product_scales.c.id == product_scale_id)
        statement = _locked(
            select(Product).where(products.c.id == owner.scalar_subquery()), for_update
        )
        return (await self._session.execute(statement)).scalar_one_or_none()

    async def get_for_variant(
        self, variant_id: UUID, *, for_update: bool = False
    ) -> Product | None:
        owner = (
            select(product_scales.c.product_id)
            .join(variants, variants.c.product_scale_id == product_scales.c.id)
            .where(variants.c.id == variant_id)
        )
        statement = _locked(
            select(Product).where(products.c.id == owner.scalar_subquery()), for_update
        )
        return (await self._session.execute(statement)).scalar_one_or_none()

    async def slug_taken(self, slug: str, *, except_id: UUID | None = None) -> bool:
        condition = products.c.slug == slug
        if except_id is not None:
            condition = condition & (products.c.id != except_id)
        return bool(await self._session.scalar(select(exists().where(condition))))

    async def next_number(self) -> int:
        return int(await self._session.scalar(select(product_number_seq.next_value())) or 0)

    async def next_gtin_serial(self) -> int:
        return int(await self._session.scalar(select(gtin_serial_seq.next_value())) or 0)

    def add(self, product: Product) -> None:
        self._session.add(product)

    def mark_changed(self, product: Product) -> None:
        # The version column only moves when the product row itself is updated. Changes
        # to scales, variants or the gallery touch updated_at, but within the same
        # microsecond that would be no change at all; flagging it forces the UPDATE.
        flag_modified(product, "updated_at")

    async def delete(self, product: Product) -> None:
        await self._session.delete(product)

    async def articles(self) -> list[Article]:
        statement = (
            select(
                products.c.name,
                products.c.status,
                categories.c.name.label("category_name"),
                scales.c.name.label("scale_name"),
                finishes.c.name.label("finish_name"),
                variants.c.color,
                variants.c.sku,
                variants.c.gtin,
                variants.c.price_cents,
                variants.c.active,
                variants.c.allow_backorder,
                variants.c.lead_time_min_weeks,
                variants.c.lead_time_max_weeks,
            )
            .join(product_scales, product_scales.c.id == variants.c.product_scale_id)
            .join(products, products.c.id == product_scales.c.product_id)
            .join(scales, scales.c.code == product_scales.c.scale_code)
            .join(finishes, finishes.c.code == variants.c.finish_code)
            .outerjoin(categories, categories.c.id == products.c.primary_category_id)
            .where(products.c.status != ProductStatus.ARCHIVED)
            .order_by(
                products.c.name,
                scales.c.ratio_denominator.desc(),
                finishes.c.position,
                variants.c.color,
            )
        )
        return [
            Article(
                product_name=row.name,
                product_status=str(row.status),
                category_name=row.category_name,
                scale_name=row.scale_name,
                finish_name=row.finish_name,
                color=row.color,
                sku=row.sku,
                gtin=row.gtin,
                price_cents=row.price_cents,
                active=row.active and row.status == ProductStatus.ACTIVE,
                allow_backorder=row.allow_backorder,
                lead_time_weeks=(
                    (row.lead_time_min_weeks, row.lead_time_max_weeks)
                    if row.lead_time_min_weeks is not None
                    else None
                ),
            )
            for row in await self._session.execute(statement)
        ]

    async def offered_counts(self) -> dict[tuple[UUID, str], int]:
        statement = (
            select(products.c.primary_category_id, product_scales.c.scale_code, func.count())
            .join(product_scales, product_scales.c.product_id == products.c.id)
            .where(
                products.c.status == ProductStatus.ACTIVE,
                products.c.primary_category_id.is_not(None),
                exists().where(
                    variants.c.product_scale_id == product_scales.c.id,
                    variants.c.active.is_(True),
                ),
            )
            .group_by(products.c.primary_category_id, product_scales.c.scale_code)
        )
        return {
            (category_id, scale_code): count
            for category_id, scale_code, count in await self._session.execute(statement)
        }

    async def search(self, query: ProductQuery) -> list[Product]:
        statement = select(Product)
        if query.statuses is not None:
            statement = statement.where(products.c.status.in_(sorted(query.statuses)))
        if query.category_ids is not None:
            statement = statement.where(products.c.primary_category_id.in_(query.category_ids))
        if query.scale_code is not None:
            # Offered in the scale: at least one active variant in it.
            statement = statement.where(
                exists().where(
                    product_scales.c.product_id == products.c.id,
                    product_scales.c.scale_code == query.scale_code,
                    variants.c.product_scale_id == product_scales.c.id,
                    variants.c.active.is_(True),
                )
            )
        if query.epoch_code is not None:
            statement = statement.where(
                exists().where(
                    product_epochs.c.product_id == products.c.id,
                    product_epochs.c.epoch_code == query.epoch_code,
                )
            )
        if query.text:
            statement = statement.where(
                products.c.search_vector.op("@@")(func.websearch_to_tsquery("german", query.text))
            )
        statement = _ordered(statement, query.order, query.after).limit(query.limit)
        return list((await self._session.execute(statement)).scalars())


# The "from" price: the cheapest active variant, as Product.lowest_price_cents computes it.
_LOWEST_PRICE = (
    select(func.min(variants.c.price_cents))
    .join(product_scales, product_scales.c.id == variants.c.product_scale_id)
    .where(product_scales.c.product_id == products.c.id, variants.c.active.is_(True))
    .correlate(products)
    .scalar_subquery()
)


def _ordered[*Ts](
    statement: Select[*Ts], order: ProductOrder, after: ProductCursor | None
) -> Select[*Ts]:
    """Sort a product query and continue after the cursor (keyset: sort value, then id)."""
    key: ColumnElement[Any]
    value: object
    match order:
        case ProductOrder.PUBLISHED:
            key, value = products.c.published_at, after.published_at if after else None
            descending = True
        case ProductOrder.PRICE_ASC | ProductOrder.PRICE_DESC:
            key, value = _LOWEST_PRICE, after.price_cents if after else None
            descending = order is ProductOrder.PRICE_DESC
        case ProductOrder.NAME:
            key, value = products.c.name, after.name if after else None
            descending = False
        case ProductOrder.CREATED:
            # Ids are UUIDv7: descending id is newest first.
            statement = statement.order_by(products.c.id.desc())
            return statement if after is None else statement.where(products.c.id < after.id)
    if descending:
        statement = statement.order_by(key.desc(), products.c.id.desc())
    else:
        statement = statement.order_by(key.asc(), products.c.id.asc())
    if after is None or value is None:
        return statement
    position = tuple_(key, products.c.id)
    cursor = tuple_(literal(value), literal(after.id))
    return statement.where(position < cursor if descending else position > cursor)


class SqlCategoryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def all(self) -> list[Category]:
        statement = select(Category).order_by(categories.c.position, categories.c.name)
        return list((await self._session.execute(statement)).scalars())

    async def get(self, category_id: UUID, *, for_update: bool = False) -> Category | None:
        statement = _locked(select(Category).where(categories.c.id == category_id), for_update)
        return (await self._session.execute(statement)).scalar_one_or_none()

    async def get_by_slug(self, slug: str) -> Category | None:
        statement = select(Category).where(categories.c.slug == slug)
        return (await self._session.execute(statement)).scalar_one_or_none()

    async def slug_taken(self, slug: str, *, except_id: UUID | None = None) -> bool:
        condition = categories.c.slug == slug
        if except_id is not None:
            condition = condition & (categories.c.id != except_id)
        return bool(await self._session.scalar(select(exists().where(condition))))

    def add(self, category: Category) -> None:
        self._session.add(category)


class SqlReferenceData:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def scales(self) -> list[Scale]:
        statement = select(Scale).order_by(scales.c.ratio_denominator.desc(), scales.c.code)
        return list((await self._session.execute(statement)).scalars())

    async def get_scale(self, code: str, *, for_update: bool = False) -> Scale | None:
        statement = select(Scale).where(scales.c.code == code)
        if for_update:
            # A full row lock: inserting a product's scale takes a key-share lock on this
            # row, so deleting waits for such inserts and they wait for the delete.
            statement = statement.with_for_update().execution_options(populate_existing=True)
        return (await self._session.execute(statement)).scalar_one_or_none()

    async def scale_taken(
        self, *, code: str | None = None, name: str | None = None, except_code: str | None = None
    ) -> bool:
        conditions: list[ColumnElement[bool]] = []
        if code is not None:
            conditions.append(scales.c.code == code)
        if name is not None:
            conditions.append(scales.c.name == name)
        if not conditions:
            return False
        if except_code is not None:
            conditions.append(scales.c.code != except_code)
        # Compare with what is stored: flushing a pending rename first would hit the
        # unique constraint before this check could answer.
        with self._session.no_autoflush:
            return bool(await self._session.scalar(select(exists().where(*conditions))))

    async def scale_usage(self) -> dict[str, int]:
        statement = select(product_scales.c.scale_code, func.count()).group_by(
            product_scales.c.scale_code
        )
        return {str(code): int(count) for code, count in await self._session.execute(statement)}

    async def scale_in_use(self, code: str) -> bool:
        offered = exists().where(product_scales.c.scale_code == code)
        tagged = exists().where(product_media.c.scale_code == code)
        return bool(await self._session.scalar(select(offered | tagged)))

    def add_scale(self, scale: Scale) -> None:
        self._session.add(scale)

    async def delete_scale(self, scale: Scale) -> None:
        await self._session.delete(scale)

    async def finishes(self) -> list[Finish]:
        rows = await self._session.execute(select(finishes).order_by(finishes.c.position))
        return [
            Finish(
                code=row.code,
                name=row.name,
                sku_letter=row.sku_letter,
                position=row.position,
                colored=row.colored,
                offered=row.offered,
            )
            for row in rows
        ]

    async def epochs(self) -> list[Epoch]:
        rows = await self._session.execute(select(epochs).order_by(epochs.c.position))
        return [
            Epoch(code=row.code, name=row.name, period=row.period, position=row.position)
            for row in rows
        ]


class SqlImages:
    """The media module's image facade, inside this unit of work's transaction."""

    def __init__(self, uow: UnitOfWork, public_base_url: str) -> None:
        self._uow = uow
        self._public_base_url = public_base_url

    async def load(self, asset_ids: Collection[UUID]) -> dict[UUID, ImageView]:
        return await load_images(self._uow, asset_ids, public_base_url=self._public_base_url)


class SqlCatalogUnitOfWork(UnitOfWork):
    """Unit of work with the catalogue repositories attached."""

    products: SqlProductRepository
    categories: SqlCategoryRepository
    references: SqlReferenceData
    images: SqlImages

    def __init__(
        self, session_factory: async_sessionmaker[AsyncSession], *, public_base_url: str
    ) -> None:
        super().__init__(session_factory)
        self._public_base_url = public_base_url

    def _attach(self, session: AsyncSession) -> None:
        start_mappers()
        self.products = SqlProductRepository(session)
        self.categories = SqlCategoryRepository(session)
        self.references = SqlReferenceData(session)
        self.images = SqlImages(self, self._public_base_url)


def catalog_uow_factory(
    session_factory: async_sessionmaker[AsyncSession], *, public_base_url: str
) -> partial[SqlCatalogUnitOfWork]:
    """The factory the catalogue service gets: a fresh unit of work per call."""
    return partial(SqlCatalogUnitOfWork, session_factory, public_base_url=public_base_url)
