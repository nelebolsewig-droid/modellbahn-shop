"""Catalogue use cases: categories, products with scales and variants, galleries, the shop.

Every public method runs in its own unit of work. Changes to a product lock its row
and compare the version the client read (``expected_version``, from ``If-Match``),
so two people editing the same product cannot overwrite each other unnoticed.
"""

from collections.abc import Awaitable, Callable, Collection
from dataclasses import dataclass
from datetime import datetime
from typing import Final
from uuid import UUID

from modellbahn.modules.catalog.application.cursors import decode_cursor, encode_cursor
from modellbahn.modules.catalog.application.ports import (
    CatalogUnitOfWork,
    ProductCursor,
    ProductOrder,
    ProductQuery,
)
from modellbahn.modules.catalog.domain.errors import (
    CategoryCycleError,
    CategoryNotFoundError,
    InvalidFieldError,
    ProductNotFoundError,
    ProductScaleNotFoundError,
    PublishBlocker,
    ScaleAlreadyAddedError,
    SlugTakenError,
    UnknownReferenceError,
    VariantAlreadyExistsError,
    VariantHasUnitsError,
    VariantNotFoundError,
    VersionMismatchError,
)
from modellbahn.modules.catalog.domain.model import (
    UNSET,
    Category,
    Dimensions,
    Epoch,
    Finish,
    GalleryEntry,
    Maybe,
    Product,
    ProductStatus,
    Scale,
    VariantDraft,
    internal_gtin,
)
from modellbahn.modules.catalog.domain.text import check_slug, slugify
from modellbahn.modules.media.contracts.images import AssetStatus, ImageView
from modellbahn.platform.clock import Clock
from modellbahn.platform.events import DomainEvent
from modellbahn.platform.uow import (
    ConcurrentUpdateError,
    ForeignKeyViolationError,
    UniqueViolationError,
)

type UnitOfWorkFactory = Callable[[], CatalogUnitOfWork]
type ProductChange = Callable[[CatalogUnitOfWork, Product, datetime], Awaitable[list[DomainEvent]]]

ADMIN_PAGE_MAX: Final = 100
STORE_PAGE_MAX: Final = 48
# Images that may join a gallery: the upload is complete (processing may still run).
_ATTACHABLE: Final = frozenset({AssetStatus.UPLOADED, AssetStatus.READY})
# Unique constraints that stand for a rule of the model.
_UNITS_OF_VARIANT: Final = "fk_units_variant_id_variants"
_UNIQUE_RULES: Final[dict[str, type[Exception]]] = {
    "uq_products_slug": SlugTakenError,
    "uq_categories_slug": SlugTakenError,
    "uq_product_scales_product_id_scale_code": ScaleAlreadyAddedError,
    "uq_variants_product_scale_id_finish_code": VariantAlreadyExistsError,
}


@dataclass(frozen=True, slots=True)
class References:
    """Scales, finishes and epochs, each in display order."""

    scales: list[Scale]
    finishes: list[Finish]
    epochs: list[Epoch]

    def scale(self, code: str, *, field: str = "scale_code") -> Scale:
        found = next((s for s in self.scales if s.code == code), None)
        if found is None:
            raise UnknownReferenceError(field, code)
        return found

    def finish(self, code: str, *, field: str = "finish_code") -> Finish:
        found = next((f for f in self.finishes if f.code == code), None)
        if found is None:
            raise UnknownReferenceError(field, code)
        return found

    def check_epochs(self, codes: Collection[str], *, field: str = "epoch_codes") -> None:
        known = {epoch.code for epoch in self.epochs}
        for code in codes:
            if code not in known:
                raise UnknownReferenceError(field, code)


@dataclass(frozen=True, slots=True)
class ProductDetails:
    """A product with the images of its gallery and what keeps it out of the shop."""

    product: Product
    images: dict[UUID, ImageView]
    blockers: list[PublishBlocker]


@dataclass(frozen=True, slots=True)
class ProductCard:
    """A product in a list, with its main image (if the media module has it)."""

    product: Product
    main_image: ImageView | None


@dataclass(frozen=True, slots=True)
class ProductPage:
    items: list[ProductCard]
    next_cursor: str | None


@dataclass(frozen=True, slots=True)
class Navigation:
    """What the shop's menus need, with how many products each choice would show."""

    categories: list[Category]
    references: References
    # Products in the shop per (category, scale code), in that category itself only.
    offered: dict[tuple[UUID, str], int]

    def scale_count(self, scale_code: str) -> int:
        """Products in the shop in this scale (each product has exactly one category)."""
        return sum(n for (_, code), n in self.offered.items() if code == scale_code)

    def category_counts(self, category_id: UUID) -> dict[str, int]:
        """Products directly in this category, per scale code."""
        return {code: n for (cid, code), n in self.offered.items() if cid == category_id}


@dataclass(frozen=True, slots=True)
class StoreProduct:
    """A product in the shop: ready images only, and the path of its category."""

    product: Product
    images: dict[UUID, ImageView]
    category_path: list[Category]
    references: References


class CatalogService:
    """The catalogue module's use cases, independent of HTTP."""

    def __init__(self, *, uow_factory: UnitOfWorkFactory, clock: Clock) -> None:
        self._uow = uow_factory
        self._clock = clock

    # --- Reference data and navigation --------------------------------------------------

    async def references(self) -> References:
        async with self._uow() as uow:
            return await _references(uow)

    async def navigation(self) -> Navigation:
        async with self._uow() as uow:
            return Navigation(
                categories=await uow.categories.all(),
                references=await _references(uow),
                offered=await uow.products.offered_counts(),
            )

    # --- Categories ---------------------------------------------------------------------

    async def list_categories(self) -> list[Category]:
        async with self._uow() as uow:
            return await uow.categories.all()

    async def create_category(
        self,
        *,
        name: str,
        slug: str | None = None,
        parent_id: UUID | None = None,
        position: int | None = None,
    ) -> Category:
        now = self._clock.now()
        async with self._uow() as uow:
            existing = await uow.categories.all()
            if parent_id is not None and not any(c.id == parent_id for c in existing):
                raise UnknownReferenceError("parent_id", str(parent_id))
            address = check_slug(slug) if slug is not None else slugify(name)
            if await uow.categories.slug_taken(address):
                raise SlugTakenError
            siblings = [c for c in existing if c.parent_id == parent_id]
            category = Category.create(
                name=name,
                slug=address,
                parent_id=parent_id,
                position=len(siblings) if position is None else position,
                now=now,
            )
            uow.categories.add(category)
            await _commit(uow)
            return category

    async def change_category(
        self,
        category_id: UUID,
        *,
        name: Maybe[str] = UNSET,
        slug: Maybe[str] = UNSET,
        parent_id: Maybe[UUID | None] = UNSET,
        position: Maybe[int] = UNSET,
    ) -> Category:
        async with self._uow() as uow:
            category = await uow.categories.get(category_id, for_update=True)
            if category is None:
                raise CategoryNotFoundError
            if parent_id is not UNSET and parent_id is not None:
                _check_no_cycle(await uow.categories.all(), category_id, parent_id)
            if (
                slug is not UNSET
                and slug != category.slug
                and await uow.categories.slug_taken(slug, except_id=category_id)
            ):
                raise SlugTakenError
            category.change(
                name=name, slug=slug, parent_id=parent_id, position=position, now=self._clock.now()
            )
            await _commit(uow)
            return category

    # --- Products: reading --------------------------------------------------------------

    async def get_product(self, product_id: UUID) -> ProductDetails:
        async with self._uow() as uow:
            product = await uow.products.get(product_id)
            if product is None:
                raise ProductNotFoundError
            return await _details(uow, product)

    async def list_products(
        self,
        *,
        status: ProductStatus | None = None,
        text: str | None = None,
        cursor: str | None = None,
        limit: int = 50,
    ) -> ProductPage:
        query = ProductQuery(
            order=ProductOrder.CREATED,
            limit=min(limit, ADMIN_PAGE_MAX),
            statuses=None if status is None else frozenset({status}),
            text=text or None,
            after=None if cursor is None else decode_cursor(cursor),
        )
        async with self._uow() as uow:
            return await _page(uow, query)

    # --- Products: changing -------------------------------------------------------------

    async def create_product(self, *, name: str, slug: str | None = None) -> ProductDetails:
        now = self._clock.now()
        async with self._uow() as uow:
            number = await uow.products.next_number()
            if slug is not None:
                address = check_slug(slug)
                if await uow.products.slug_taken(address):
                    raise SlugTakenError
            else:
                address = slugify(name)
                if await uow.products.slug_taken(address):
                    # The number makes a generated address unique.
                    address = check_slug(f"{address[:70]}-{number}")
                    if await uow.products.slug_taken(address):
                        raise SlugTakenError
            product = Product.create(number=number, name=name, slug=address, now=now)
            uow.products.add(product)
            await _commit(uow)
            return await _details(uow, product)

    async def change_product(
        self,
        product_id: UUID,
        *,
        expected_version: int | None,
        name: Maybe[str] = UNSET,
        slug: Maybe[str] = UNSET,
        summary: Maybe[str] = UNSET,
        description: Maybe[str] = UNSET,
        prototype: Maybe[str] = UNSET,
        primary_category_id: Maybe[UUID | None] = UNSET,
        epoch_codes: Maybe[list[str]] = UNSET,
    ) -> ProductDetails:
        async def change(
            uow: CatalogUnitOfWork, product: Product, now: datetime
        ) -> list[DomainEvent]:
            if (
                primary_category_id is not UNSET
                and primary_category_id is not None
                and await uow.categories.get(primary_category_id) is None
            ):
                raise UnknownReferenceError("primary_category_id", str(primary_category_id))
            if epoch_codes is not UNSET:
                (await _references(uow)).check_epochs(epoch_codes)
            if (
                slug is not UNSET
                and slug != product.slug
                and await uow.products.slug_taken(check_slug(slug), except_id=product.id)
            ):
                raise SlugTakenError
            product.change_details(
                name=name,
                slug=slug,
                summary=summary,
                description=description,
                prototype=prototype,
                primary_category_id=primary_category_id,
                epoch_codes=epoch_codes,
                now=now,
            )
            return []

        return await self._change(_by_id(product_id), expected_version, change)

    async def add_scale(
        self,
        product_id: UUID,
        *,
        expected_version: int | None,
        scale_code: str,
        dimensions: Dimensions,
    ) -> ProductDetails:
        async def change(
            uow: CatalogUnitOfWork, product: Product, now: datetime
        ) -> list[DomainEvent]:
            scale = (await _references(uow)).scale(scale_code)
            product.add_scale(scale, dimensions, now)
            return []

        return await self._change(_by_id(product_id), expected_version, change)

    async def change_scale(
        self, product_scale_id: UUID, *, expected_version: int | None, dimensions: Dimensions
    ) -> ProductDetails:
        async def change(
            uow: CatalogUnitOfWork, product: Product, now: datetime
        ) -> list[DomainEvent]:
            product.change_dimensions(product_scale_id, dimensions, now)
            return []

        return await self._change(_by_scale(product_scale_id), expected_version, change)

    async def remove_scale(
        self, product_scale_id: UUID, *, expected_version: int | None
    ) -> ProductDetails:
        async def change(
            uow: CatalogUnitOfWork, product: Product, now: datetime
        ) -> list[DomainEvent]:
            product.remove_scale(product_scale_id, now)
            return []

        return await self._change(_by_scale(product_scale_id), expected_version, change)

    async def add_variant(
        self,
        product_scale_id: UUID,
        *,
        expected_version: int | None,
        finish_code: str,
        price_cents: int,
        compare_at_price_cents: int | None = None,
        allow_backorder: bool = False,
        active: bool = True,
    ) -> ProductDetails:
        async def change(
            uow: CatalogUnitOfWork, product: Product, now: datetime
        ) -> list[DomainEvent]:
            draft = VariantDraft(
                finish=(await _references(uow)).finish(finish_code),
                price_cents=price_cents,
                compare_at_price_cents=compare_at_price_cents,
                allow_backorder=allow_backorder,
                active=active,
            )
            # Drawn before the checks: a refused variant leaves a gap, which is harmless.
            gtin = internal_gtin(await uow.products.next_gtin_serial())
            product.add_variant(product_scale_id, draft, gtin=gtin, now=now)
            return []

        return await self._change(_by_scale(product_scale_id), expected_version, change)

    async def change_variant(
        self,
        variant_id: UUID,
        *,
        expected_version: int | None,
        price_cents: Maybe[int] = UNSET,
        compare_at_price_cents: Maybe[int | None] = UNSET,
        allow_backorder: Maybe[bool] = UNSET,
        active: Maybe[bool] = UNSET,
    ) -> ProductDetails:
        async def change(
            uow: CatalogUnitOfWork, product: Product, now: datetime
        ) -> list[DomainEvent]:
            product.change_variant(
                variant_id,
                price_cents=price_cents,
                compare_at_price_cents=compare_at_price_cents,
                allow_backorder=allow_backorder,
                active=active,
                now=now,
            )
            return []

        return await self._change(_by_variant(variant_id), expected_version, change)

    async def remove_variant(
        self, variant_id: UUID, *, expected_version: int | None
    ) -> ProductDetails:
        async def change(
            uow: CatalogUnitOfWork, product: Product, now: datetime
        ) -> list[DomainEvent]:
            product.remove_variant(variant_id, now)
            return []

        return await self._change(_by_variant(variant_id), expected_version, change)

    async def attach_image(
        self, product_id: UUID, *, asset_id: UUID, alt_text: str = ""
    ) -> ProductDetails:
        """Append an uploaded image to the gallery.

        Needs no version: appending commutes, and the row lock orders concurrent
        uploads of the same gallery.
        """

        async def change(
            uow: CatalogUnitOfWork, product: Product, now: datetime
        ) -> list[DomainEvent]:
            image = (await uow.images.load([asset_id])).get(asset_id)
            if image is None:
                raise UnknownReferenceError("asset_id", str(asset_id))
            if image.status not in _ATTACHABLE:
                raise InvalidFieldError("asset_id", "not_uploaded", "the upload is not complete")
            product.attach_image(asset_id, alt_text=alt_text, now=now)
            return []

        return await self._change(_by_id(product_id), None, change)

    async def arrange_gallery(
        self, product_id: UUID, *, expected_version: int | None, entries: list[GalleryEntry]
    ) -> ProductDetails:
        async def change(
            uow: CatalogUnitOfWork, product: Product, now: datetime
        ) -> list[DomainEvent]:
            references = await _references(uow)
            for index, entry in enumerate(entries):
                if entry.finish_code is not None:
                    references.finish(entry.finish_code, field=f"entries.{index}.finish_code")
            main_ready = False
            if entries:
                main = (await uow.images.load([entries[0].asset_id])).get(entries[0].asset_id)
                main_ready = main is not None and main.is_ready
            product.arrange_gallery(entries, main_image_ready=main_ready, now=now)
            return []

        return await self._change(_by_id(product_id), expected_version, change)

    async def publish(self, product_id: UUID, *, expected_version: int | None) -> ProductDetails:
        async def change(
            uow: CatalogUnitOfWork, product: Product, now: datetime
        ) -> list[DomainEvent]:
            return [
                product.publish(main_image_ready=await _main_image_ready(uow, product), now=now)
            ]

        return await self._change(_by_id(product_id), expected_version, change)

    async def archive(self, product_id: UUID, *, expected_version: int | None) -> ProductDetails:
        async def change(
            uow: CatalogUnitOfWork, product: Product, now: datetime
        ) -> list[DomainEvent]:
            return [product.archive(now)]

        return await self._change(_by_id(product_id), expected_version, change)

    async def delete_product(self, product_id: UUID, *, expected_version: int | None) -> None:
        async with self._uow() as uow:
            product = await uow.products.get(product_id, for_update=True)
            if product is None:
                raise ProductNotFoundError
            _check_version(product, expected_version)
            product.ensure_deletable()
            await uow.products.delete(product)
            await _commit(uow)

    async def _change(
        self,
        load: Callable[[CatalogUnitOfWork], Awaitable[Product]],
        expected_version: int | None,
        change: ProductChange,
    ) -> ProductDetails:
        now = self._clock.now()
        async with self._uow() as uow:
            product = await load(uow)
            _check_version(product, expected_version)
            events = await change(uow, product, now)
            uow.products.mark_changed(product)
            notice = None if events else product.change_notice(now)
            uow.publish(*events, *([] if notice is None else [notice]))
            await _commit(uow)
            return await _details(uow, product)

    # --- The shop -----------------------------------------------------------------------

    async def store_products(
        self,
        *,
        category_slug: str | None = None,
        scale_code: str | None = None,
        epoch_code: str | None = None,
        text: str | None = None,
        order: ProductOrder = ProductOrder.PUBLISHED,
        cursor: str | None = None,
        limit: int = 24,
    ) -> ProductPage:
        """Products in the shop, newest first unless ``order`` says otherwise.

        A category includes its subcategories; a scale or an epoch narrows the list to
        products offered in it.
        """
        if order is ProductOrder.CREATED:
            msg = "the shop lists by publication, price or name"
            raise ValueError(msg)
        async with self._uow() as uow:
            category_ids: frozenset[UUID] | None = None
            if category_slug is not None:
                everything = await uow.categories.all()
                root = next((c for c in everything if c.slug == category_slug), None)
                if root is None:
                    raise CategoryNotFoundError
                category_ids = _subtree(everything, root.id)
            references = await _references(uow)
            if scale_code is not None:
                references.scale(scale_code, field="scale")
            if epoch_code is not None:
                references.check_epochs([epoch_code], field="epoch")
            query = ProductQuery(
                order=order,
                limit=min(limit, STORE_PAGE_MAX),
                statuses=frozenset({ProductStatus.ACTIVE}),
                category_ids=category_ids,
                scale_code=scale_code,
                epoch_code=epoch_code,
                text=text or None,
                after=None if cursor is None else decode_cursor(cursor),
            )
            return await _page(uow, query)

    async def store_product(self, slug: str) -> StoreProduct:
        async with self._uow() as uow:
            product = await uow.products.get_by_slug(slug)
            if product is None or not product.is_active:
                raise ProductNotFoundError
            images = await uow.images.load([entry.asset_id for entry in product.media])
            everything = {c.id: c for c in await uow.categories.all()}
            return StoreProduct(
                product=product,
                images={asset_id: image for asset_id, image in images.items() if image.is_ready},
                category_path=_path(everything, product.primary_category_id),
                references=await _references(uow),
            )


# --- Helpers ----------------------------------------------------------------------------


def _by_id(product_id: UUID) -> Callable[[CatalogUnitOfWork], Awaitable[Product]]:
    async def load(uow: CatalogUnitOfWork) -> Product:
        product = await uow.products.get(product_id, for_update=True)
        if product is None:
            raise ProductNotFoundError
        return product

    return load


def _by_scale(product_scale_id: UUID) -> Callable[[CatalogUnitOfWork], Awaitable[Product]]:
    async def load(uow: CatalogUnitOfWork) -> Product:
        product = await uow.products.get_for_scale(product_scale_id, for_update=True)
        if product is None:
            raise ProductScaleNotFoundError
        return product

    return load


def _by_variant(variant_id: UUID) -> Callable[[CatalogUnitOfWork], Awaitable[Product]]:
    async def load(uow: CatalogUnitOfWork) -> Product:
        product = await uow.products.get_for_variant(variant_id, for_update=True)
        if product is None:
            raise VariantNotFoundError
        return product

    return load


def _check_version(product: Product, expected_version: int | None) -> None:
    if expected_version is not None and expected_version != product.version:
        raise VersionMismatchError


async def _commit(uow: CatalogUnitOfWork) -> None:
    try:
        await uow.commit()
    except ConcurrentUpdateError as exc:
        raise VersionMismatchError from exc
    except ForeignKeyViolationError as exc:
        # The inventory refers to variants it has units of; removing them would lose history.
        if exc.constraint != _UNITS_OF_VARIANT:
            raise
        raise VariantHasUnitsError from exc
    except UniqueViolationError as exc:
        rule = _UNIQUE_RULES.get(exc.constraint or "")
        if rule is None:
            raise
        raise rule from exc


async def _references(uow: CatalogUnitOfWork) -> References:
    return References(
        scales=await uow.references.scales(),
        finishes=await uow.references.finishes(),
        epochs=await uow.references.epochs(),
    )


async def _main_image_ready(uow: CatalogUnitOfWork, product: Product) -> bool:
    main = product.main_image
    if main is None:
        return False
    image = (await uow.images.load([main.asset_id])).get(main.asset_id)
    return image is not None and image.is_ready


async def _details(uow: CatalogUnitOfWork, product: Product) -> ProductDetails:
    images = await uow.images.load([entry.asset_id for entry in product.media])
    main = product.main_image
    main_ready = main is not None and main.asset_id in images and images[main.asset_id].is_ready
    return ProductDetails(
        product=product,
        images=images,
        blockers=product.publish_blockers(main_image_ready=main_ready),
    )


async def _page(uow: CatalogUnitOfWork, query: ProductQuery) -> ProductPage:
    # One more than asked for tells whether another page follows.
    found = await uow.products.search(
        ProductQuery(
            order=query.order,
            limit=query.limit + 1,
            statuses=query.statuses,
            category_ids=query.category_ids,
            scale_code=query.scale_code,
            epoch_code=query.epoch_code,
            text=query.text,
            after=query.after,
        )
    )
    page, more = found[: query.limit], len(found) > query.limit
    mains = {p.id: p.main_image for p in page}
    images = await uow.images.load([m.asset_id for m in mains.values() if m is not None])
    items = []
    for product in page:
        main = mains[product.id]
        items.append(
            ProductCard(
                product=product, main_image=None if main is None else images.get(main.asset_id)
            )
        )
    next_cursor = None
    if more and page:
        last = page[-1]
        next_cursor = encode_cursor(_cursor_after(last, query.order))
    return ProductPage(items=items, next_cursor=next_cursor)


def _cursor_after(product: Product, order: ProductOrder) -> ProductCursor:
    match order:
        case ProductOrder.PUBLISHED:
            return ProductCursor(id=product.id, published_at=product.published_at)
        case ProductOrder.PRICE_ASC | ProductOrder.PRICE_DESC:
            return ProductCursor(id=product.id, price_cents=product.lowest_price_cents)
        case ProductOrder.NAME:
            return ProductCursor(id=product.id, name=product.name)
        case ProductOrder.CREATED:
            return ProductCursor(id=product.id)


def _check_no_cycle(categories: list[Category], category_id: UUID, parent_id: UUID) -> None:
    parents = {c.id: c.parent_id for c in categories}
    if parent_id not in parents:
        raise UnknownReferenceError("parent_id", str(parent_id))
    current: UUID | None = parent_id
    while current is not None:
        if current == category_id:
            raise CategoryCycleError
        current = parents.get(current)


def _subtree(categories: list[Category], root_id: UUID) -> frozenset[UUID]:
    children: dict[UUID | None, list[UUID]] = {}
    for category in categories:
        children.setdefault(category.parent_id, []).append(category.id)
    found: set[UUID] = set()
    pending = [root_id]
    while pending:
        current = pending.pop()
        if current not in found:
            found.add(current)
            pending.extend(children.get(current, []))
    return frozenset(found)


def _path(categories: dict[UUID, Category], category_id: UUID | None) -> list[Category]:
    path: list[Category] = []
    current = category_id
    while current is not None and current in categories and len(path) < len(categories):
        category = categories[current]
        path.append(category)
        current = category.parent_id
    return list(reversed(path))
