"""Request and response bodies of the catalogue API (snake_case JSON).

Prices are cents (gross). Lengths are millimetres with one decimal, sent as numbers.
"""

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from modellbahn.modules.catalog.application.scales import ScaleUsage
from modellbahn.modules.catalog.application.services import (
    Navigation,
    ProductCard,
    ProductDetails,
    ProductPage,
    References,
    StoreProduct,
)
from modellbahn.modules.catalog.domain.errors import PublishBlocker
from modellbahn.modules.catalog.domain.model import (
    ALT_TEXT_MAX_LENGTH,
    CATEGORY_NAME_MAX_LENGTH,
    DESCRIPTION_MAX_LENGTH,
    PRICE_MAX_CENTS,
    PRODUCT_NAME_MAX_LENGTH,
    PROTOTYPE_MAX_LENGTH,
    SCALE_NAME_MAX_LENGTH,
    SUMMARY_MAX_LENGTH,
    WEIGHT_MAX_G,
    Category,
    Dimensions,
    Epoch,
    Finish,
    GalleryEntry,
    MediaRole,
    ProductScale,
    ProductStatus,
    Scale,
    Variant,
)
from modellbahn.modules.catalog.domain.text import SLUG_MAX_LENGTH
from modellbahn.modules.media.contracts.images import AssetStatus, ImageView, RenditionFormat

Slug = Annotated[
    str, Field(min_length=1, max_length=SLUG_MAX_LENGTH, examples=["stellwerk-altenau"])
]
Price = Annotated[int, Field(ge=0, le=PRICE_MAX_CENTS, examples=[4990])]
Millimetres = Annotated[float, Field(gt=0, le=10_000, examples=[112.5])]
Grams = Annotated[int, Field(gt=0, le=WEIGHT_MAX_G)]


class _Request(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _decimal(value: float | None) -> Decimal | None:
    return None if value is None else Decimal(str(round(value, 1)))


def _float(value: Decimal | None) -> float | None:
    return None if value is None else float(value)


# --- Reference data -------------------------------------------------------------------


class ScaleOut(BaseModel):
    code: str = Field(
        examples=["H0"], description="Fixed once created; part of SKUs and addresses."
    )
    name: str = Field(examples=["H0"])
    ratio: str = Field(examples=["1:87"], description="Written the German way: 1:87, 1:22,5.")
    ratio_denominator: float = Field(examples=[87])
    track_gauge_mm: float | None = Field(
        examples=[16.5], description="Null for scales without a track, e.g. road vehicles."
    )

    @classmethod
    def from_scale(cls, scale: Scale) -> Self:
        return cls(
            code=scale.code,
            name=scale.name,
            ratio=scale.ratio,
            ratio_denominator=float(scale.ratio_denominator),
            track_gauge_mm=_float(scale.track_gauge_mm),
        )


class AdminScaleOut(ScaleOut):
    product_count: int = Field(description="Products offered in it, in any state.")

    @classmethod
    def from_usage(cls, usage: ScaleUsage) -> Self:
        return cls(
            **ScaleOut.from_scale(usage.scale).model_dump(), product_count=usage.product_count
        )


class ScaleCreateIn(_Request):
    code: Annotated[str, Field(min_length=1, max_length=4, examples=["124"])]
    name: Annotated[str, Field(min_length=1, max_length=SCALE_NAME_MAX_LENGTH, examples=["1:24"])]
    ratio_denominator: Annotated[float, Field(gt=1, le=1000, examples=[24])]
    track_gauge_mm: Annotated[float, Field(gt=0, lt=1000)] | None = None


class ScalePatchIn(_Request):
    """Only the fields sent are changed; ``track_gauge_mm: null`` removes the track gauge."""

    name: Annotated[str, Field(min_length=1, max_length=SCALE_NAME_MAX_LENGTH)] | None = None
    ratio_denominator: Annotated[float, Field(gt=1, le=1000)] | None = None
    track_gauge_mm: Annotated[float, Field(gt=0, lt=1000)] | None = None


def exact_decimal(value: float) -> Decimal:
    """The number as typed (22.5 stays 22.5); the model checks the decimal places."""
    return Decimal(repr(value))


class FinishOut(BaseModel):
    code: str = Field(examples=["painted"])
    name: str = Field(examples=["bemalt"])
    sku_letter: str = Field(examples=["B"])

    @classmethod
    def from_finish(cls, finish: Finish) -> Self:
        return cls(code=finish.code, name=finish.name, sku_letter=finish.sku_letter)


class EpochOut(BaseModel):
    code: str = Field(examples=["III"])
    name: str = Field(examples=["Epoche III"])
    period: str = Field(examples=["1949–1970"])  # noqa: RUF001 - the typographic dash

    @classmethod
    def from_epoch(cls, epoch: Epoch) -> Self:
        return cls(code=epoch.code, name=epoch.name, period=epoch.period)


class ReferencesOut(BaseModel):
    """Scales, finishes and epochs, each in display order."""

    scales: list[ScaleOut]
    finishes: list[FinishOut]
    epochs: list[EpochOut]

    @classmethod
    def from_references(cls, references: References) -> Self:
        return cls(
            scales=[ScaleOut.from_scale(s) for s in references.scales],
            finishes=[FinishOut.from_finish(f) for f in references.finishes],
            epochs=[EpochOut.from_epoch(e) for e in references.epochs],
        )


# --- Categories -----------------------------------------------------------------------


class CategoryOut(BaseModel):
    id: UUID
    parent_id: UUID | None
    slug: str
    name: str
    position: int

    @classmethod
    def from_category(cls, category: Category) -> Self:
        return cls(
            id=category.id,
            parent_id=category.parent_id,
            slug=category.slug,
            name=category.name,
            position=category.position,
        )


class CategoryCreateIn(_Request):
    name: Annotated[str, Field(min_length=1, max_length=CATEGORY_NAME_MAX_LENGTH)]
    # Derived from the name when left out.
    slug: Slug | None = None
    parent_id: UUID | None = None
    position: Annotated[int, Field(ge=0)] | None = None


class CategoryPatchIn(_Request):
    """Only the fields sent are changed; ``parent_id: null`` moves to the top level."""

    name: Annotated[str, Field(min_length=1, max_length=CATEGORY_NAME_MAX_LENGTH)] | None = None
    slug: Slug | None = None
    parent_id: UUID | None = None
    position: Annotated[int, Field(ge=0)] | None = None


# --- Images ---------------------------------------------------------------------------


class ImageRenditionOut(BaseModel):
    name: str = Field(examples=["md"])
    format: RenditionFormat
    width: int
    height: int
    url: str


class ImageOut(BaseModel):
    """A ready image: placeholder, dominant colour and every rendered size."""

    asset_id: UUID
    width: int
    height: int
    dominant_color: str = Field(examples=["#c8c8be"])
    lqip: str
    renditions: list[ImageRenditionOut]

    @classmethod
    def from_view(cls, view: ImageView) -> Self | None:
        if view.width is None or view.height is None or view.lqip is None:
            return None
        return cls(
            asset_id=view.asset_id,
            width=view.width,
            height=view.height,
            dominant_color=view.dominant_color or "#ecece8",
            lqip=view.lqip,
            renditions=[_rendition(r) for r in view.renditions],
        )


class AdminImageOut(BaseModel):
    """An image in any state; facts and sizes follow once it is ready."""

    asset_id: UUID
    status: AssetStatus
    filename: str
    failure_code: str | None
    width: int | None
    height: int | None
    dominant_color: str | None
    lqip: str | None
    renditions: list[ImageRenditionOut]

    @classmethod
    def from_view(cls, view: ImageView) -> Self:
        return cls(
            asset_id=view.asset_id,
            status=view.status,
            filename=view.filename,
            failure_code=None if view.failure_code is None else view.failure_code.value,
            width=view.width,
            height=view.height,
            dominant_color=view.dominant_color,
            lqip=view.lqip,
            renditions=[_rendition(r) for r in view.renditions],
        )


def _rendition(rendition: object) -> ImageRenditionOut:
    return ImageRenditionOut.model_validate(rendition, from_attributes=True)


# --- Products (admin) -----------------------------------------------------------------


class VariantOut(BaseModel):
    id: UUID
    finish_code: str
    sku: str = Field(examples=["MB-000042-H0-B"])
    gtin: str = Field(examples=["2000000000428"])
    price_cents: int
    compare_at_price_cents: int | None
    allow_backorder: bool
    active: bool

    @classmethod
    def from_variant(cls, variant: Variant) -> Self:
        return cls(
            id=variant.id,
            finish_code=variant.finish_code,
            sku=variant.sku,
            gtin=variant.gtin,
            price_cents=variant.price_cents,
            compare_at_price_cents=variant.compare_at_price_cents,
            allow_backorder=variant.allow_backorder,
            active=variant.active,
        )


class ProductScaleOut(BaseModel):
    id: UUID
    scale_code: str
    length_mm: float | None
    width_mm: float | None
    height_mm: float | None
    weight_g: int | None
    variants: list[VariantOut]

    @classmethod
    def from_scale(cls, product_scale: ProductScale) -> Self:
        return cls(
            id=product_scale.id,
            scale_code=product_scale.scale_code,
            length_mm=_float(product_scale.length_mm),
            width_mm=_float(product_scale.width_mm),
            height_mm=_float(product_scale.height_mm),
            weight_g=product_scale.weight_g,
            variants=[VariantOut.from_variant(v) for v in product_scale.variants],
        )


class GalleryItemOut(BaseModel):
    asset_id: UUID
    position: int
    role: MediaRole
    alt_text: str
    scale_code: str | None
    finish_code: str | None
    # Null only if the media module no longer knows the asset.
    image: AdminImageOut | None


class ProductOut(BaseModel):
    """A product as the admin area edits it. ``version`` is also sent as ETag."""

    id: UUID
    number: int
    slug: str
    name: str
    summary: str
    description: str
    prototype: str
    primary_category_id: UUID | None
    status: ProductStatus
    published_at: datetime | None
    archived_at: datetime | None
    created_at: datetime
    updated_at: datetime
    version: int
    epoch_codes: list[str]
    scales: list[ProductScaleOut]
    media: list[GalleryItemOut]
    # Empty when the product may go into (or stay in) the shop.
    publish_blockers: list[PublishBlocker]

    @classmethod
    def from_details(cls, details: ProductDetails) -> Self:
        product = details.product
        return cls(
            id=product.id,
            number=product.number,
            slug=product.slug,
            name=product.name,
            summary=product.summary,
            description=product.description,
            prototype=product.prototype,
            primary_category_id=product.primary_category_id,
            status=product.status,
            published_at=product.published_at,
            archived_at=product.archived_at,
            created_at=product.created_at,
            updated_at=product.updated_at,
            version=product.version,
            epoch_codes=product.epoch_codes,
            scales=[ProductScaleOut.from_scale(s) for s in product.scales],
            media=[
                GalleryItemOut(
                    asset_id=entry.asset_id,
                    position=entry.position,
                    role=entry.role,
                    alt_text=entry.alt_text,
                    scale_code=entry.scale_code,
                    finish_code=entry.finish_code,
                    image=None
                    if entry.asset_id not in details.images
                    else AdminImageOut.from_view(details.images[entry.asset_id]),
                )
                for entry in product.gallery
            ],
            publish_blockers=details.blockers,
        )


class ProductListItemOut(BaseModel):
    id: UUID
    number: int
    slug: str
    name: str
    status: ProductStatus
    published_at: datetime | None
    updated_at: datetime
    scale_codes: list[str]
    variant_count: int
    # Lowest price of the active variants; null without any.
    price_from_cents: int | None
    main_image: AdminImageOut | None

    @classmethod
    def from_card(cls, card: ProductCard) -> Self:
        product = card.product
        return cls(
            id=product.id,
            number=product.number,
            slug=product.slug,
            name=product.name,
            status=product.status,
            published_at=product.published_at,
            updated_at=product.updated_at,
            scale_codes=[s.scale_code for s in product.scales],
            variant_count=len(product.variants),
            price_from_cents=_price_from(product.variants),
            main_image=None
            if card.main_image is None
            else AdminImageOut.from_view(card.main_image),
        )


class ProductPageOut(BaseModel):
    items: list[ProductListItemOut]
    # Pass as ``cursor`` for the next page; null on the last one.
    next_cursor: str | None

    @classmethod
    def from_page(cls, page: ProductPage) -> Self:
        return cls(
            items=[ProductListItemOut.from_card(c) for c in page.items],
            next_cursor=page.next_cursor,
        )


def _price_from(variants: list[Variant]) -> int | None:
    return min((v.price_cents for v in variants if v.active), default=None)


class ProductCreateIn(_Request):
    name: Annotated[str, Field(min_length=1, max_length=PRODUCT_NAME_MAX_LENGTH)]
    # Derived from the name when left out.
    slug: Slug | None = None


class ProductPatchIn(_Request):
    """Only the fields sent are changed; ``primary_category_id: null`` removes the category."""

    name: Annotated[str, Field(min_length=1, max_length=PRODUCT_NAME_MAX_LENGTH)] | None = None
    slug: Slug | None = None
    summary: Annotated[str, Field(max_length=SUMMARY_MAX_LENGTH)] | None = None
    description: Annotated[str, Field(max_length=DESCRIPTION_MAX_LENGTH)] | None = None
    prototype: Annotated[str, Field(max_length=PROTOTYPE_MAX_LENGTH)] | None = None
    primary_category_id: UUID | None = None
    epoch_codes: Annotated[list[str], Field(max_length=10)] | None = None


class DimensionsIn(_Request):
    """Size and weight of the model in this scale; null where unknown."""

    length_mm: Millimetres | None = None
    width_mm: Millimetres | None = None
    height_mm: Millimetres | None = None
    weight_g: Grams | None = None

    def to_dimensions(self) -> Dimensions:
        return Dimensions(
            length_mm=_decimal(self.length_mm),
            width_mm=_decimal(self.width_mm),
            height_mm=_decimal(self.height_mm),
            weight_g=self.weight_g,
        )


class ProductScaleIn(DimensionsIn):
    scale_code: str = Field(examples=["H0"])


class VariantCreateIn(_Request):
    finish_code: str = Field(examples=["painted"])
    price_cents: Price
    # A former price, shown struck through; must be above the price.
    compare_at_price_cents: Price | None = None
    allow_backorder: bool = False
    active: bool = True


class VariantPatchIn(_Request):
    """Only the fields sent are changed."""

    price_cents: Price | None = None
    compare_at_price_cents: Price | None = None
    allow_backorder: bool | None = None
    active: bool | None = None


class GalleryAttachIn(_Request):
    asset_id: UUID
    alt_text: Annotated[str, Field(max_length=ALT_TEXT_MAX_LENGTH)] = ""


class GalleryEntryIn(_Request):
    asset_id: UUID
    role: MediaRole = MediaRole.GALLERY
    alt_text: Annotated[str, Field(max_length=ALT_TEXT_MAX_LENGTH)] = ""
    scale_code: str | None = None
    finish_code: str | None = None

    def to_entry(self) -> GalleryEntry:
        return GalleryEntry(
            asset_id=self.asset_id,
            role=self.role,
            alt_text=self.alt_text,
            scale_code=self.scale_code,
            finish_code=self.finish_code,
        )


class GalleryIn(_Request):
    """The whole gallery in order; the first image is the main image."""

    entries: Annotated[list[GalleryEntryIn], Field(max_length=40)]


# --- The shop -------------------------------------------------------------------------


class NavigationScaleOut(ScaleOut):
    product_count: int = Field(description="Products in the shop in this scale.")


class NavigationCategoryOut(CategoryOut):
    product_counts: dict[str, int] = Field(
        description=(
            "Products in the shop directly in this category, per scale code; scales "
            "without any are left out. Add the subcategories for the whole branch."
        ),
        examples=[{"H0": 4, "N": 1}],
    )


class NavigationOut(BaseModel):
    """Categories (flat, with ``parent_id``), scales by size and the other reference
    data, with how many products each choice shows."""

    categories: list[NavigationCategoryOut]
    scales: list[NavigationScaleOut]
    finishes: list[FinishOut]
    epochs: list[EpochOut]

    @classmethod
    def from_navigation(cls, navigation: Navigation) -> Self:
        references = navigation.references
        return cls(
            categories=[
                NavigationCategoryOut(
                    **CategoryOut.from_category(category).model_dump(),
                    product_counts=navigation.category_counts(category.id),
                )
                for category in navigation.categories
            ],
            scales=[
                NavigationScaleOut(
                    **ScaleOut.from_scale(scale).model_dump(),
                    product_count=navigation.scale_count(scale.code),
                )
                for scale in references.scales
            ],
            finishes=[FinishOut.from_finish(f) for f in references.finishes],
            epochs=[EpochOut.from_epoch(e) for e in references.epochs],
        )


class StoreProductCardOut(BaseModel):
    slug: str
    number: int
    name: str
    summary: str
    # Scales with at least one variant for sale, in display order.
    scale_codes: list[str]
    price_from_cents: int | None
    image: ImageOut | None


class StoreProductPageOut(BaseModel):
    items: list[StoreProductCardOut]
    next_cursor: str | None

    @classmethod
    def from_page(cls, page: ProductPage, *, scale_order: list[str]) -> Self:
        items: list[StoreProductCardOut] = []
        for card in page.items:
            product = card.product
            on_sale = {s.scale_code for s in product.scales if any(v.active for v in s.variants)}
            items.append(
                StoreProductCardOut(
                    slug=product.slug,
                    number=product.number,
                    name=product.name,
                    summary=product.summary,
                    scale_codes=[code for code in scale_order if code in on_sale],
                    price_from_cents=_price_from(product.variants),
                    image=None if card.main_image is None else ImageOut.from_view(card.main_image),
                )
            )
        return cls(items=items, next_cursor=page.next_cursor)


class StoreVariantOut(BaseModel):
    id: UUID
    finish_code: str
    sku: str
    price_cents: int
    compare_at_price_cents: int | None


class StoreScaleOut(BaseModel):
    code: str
    name: str
    ratio: str
    track_gauge_mm: float | None
    length_mm: float | None
    width_mm: float | None
    height_mm: float | None
    weight_g: int | None
    variants: list[StoreVariantOut]


class StoreGalleryItemOut(BaseModel):
    image: ImageOut
    alt_text: str
    role: MediaRole
    scale_code: str | None
    finish_code: str | None


class CategoryRefOut(BaseModel):
    slug: str
    name: str


class StoreProductOut(BaseModel):
    """A product page: scales and finishes for sale, gallery of ready images."""

    slug: str
    number: int
    name: str
    summary: str
    description: str
    prototype: str
    category_path: list[CategoryRefOut]
    epochs: list[EpochOut]
    scales: list[StoreScaleOut]
    finishes: list[FinishOut]
    gallery: list[StoreGalleryItemOut]
    published_at: datetime | None

    @classmethod
    def from_store_product(cls, found: StoreProduct) -> Self:
        product, references = found.product, found.references
        by_code = {s.scale_code: s for s in product.scales}
        scales: list[StoreScaleOut] = []
        for scale in references.scales:
            product_scale = by_code.get(scale.code)
            if product_scale is None:
                continue
            on_sale = [v for v in product_scale.variants if v.active]
            if not on_sale:
                continue
            finish_order = {f.code: f.position for f in references.finishes}
            on_sale.sort(key=lambda v: finish_order.get(v.finish_code, 0))
            scales.append(
                StoreScaleOut(
                    code=scale.code,
                    name=scale.name,
                    ratio=scale.ratio,
                    track_gauge_mm=_float(scale.track_gauge_mm),
                    length_mm=_float(product_scale.length_mm),
                    width_mm=_float(product_scale.width_mm),
                    height_mm=_float(product_scale.height_mm),
                    weight_g=product_scale.weight_g,
                    variants=[
                        StoreVariantOut(
                            id=v.id,
                            finish_code=v.finish_code,
                            sku=v.sku,
                            price_cents=v.price_cents,
                            compare_at_price_cents=v.compare_at_price_cents,
                        )
                        for v in on_sale
                    ],
                )
            )
        gallery: list[StoreGalleryItemOut] = []
        for entry in product.gallery:
            view = found.images.get(entry.asset_id)
            image = None if view is None else ImageOut.from_view(view)
            if image is not None:
                gallery.append(
                    StoreGalleryItemOut(
                        image=image,
                        alt_text=entry.alt_text or product.name,
                        role=entry.role,
                        scale_code=entry.scale_code,
                        finish_code=entry.finish_code,
                    )
                )
        epochs = [e for e in references.epochs if e.code in product.epoch_codes]
        return cls(
            slug=product.slug,
            number=product.number,
            name=product.name,
            summary=product.summary,
            description=product.description,
            prototype=product.prototype,
            category_path=[CategoryRefOut(slug=c.slug, name=c.name) for c in found.category_path],
            epochs=[EpochOut.from_epoch(e) for e in epochs],
            scales=scales,
            finishes=[FinishOut.from_finish(f) for f in references.finishes],
            gallery=gallery,
            published_at=product.published_at,
        )
