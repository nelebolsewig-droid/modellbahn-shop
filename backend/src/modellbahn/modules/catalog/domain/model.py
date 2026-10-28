"""The catalogue model: products, the scales they come in, their variants and gallery.

A *product* ("Stellwerk Altenau") comes *in scales* (H0, N), and each scale is sold as
*variants*, one per finish (unbemalt, grundiert, bemalt). The product is the aggregate
root: every change goes through it and raises its version, so two people editing the
same product cannot overwrite each other unnoticed.

Plain dataclasses without any framework, mapped imperatively by the infrastructure.
Every method that depends on time takes ``now``.
"""

import re
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum, StrEnum, auto
from typing import Final, Literal
from uuid import UUID

from modellbahn.modules.catalog.domain.errors import (
    InvalidFieldError,
    InvalidProductStateError,
    ProductNotDeletableError,
    ProductNotPublishableError,
    ProductScaleNotFoundError,
    PublishBlocker,
    ScaleAlreadyAddedError,
    SlugLockedError,
    UnknownReferenceError,
    VariantAlreadyExistsError,
    VariantNotFoundError,
)
from modellbahn.modules.catalog.domain.events import (
    ProductArchived,
    ProductPublished,
    ProductUpdated,
)
from modellbahn.modules.catalog.domain.text import check_slug, multi_line, single_line
from modellbahn.platform.ids import new_id

PRODUCT_NAME_MAX_LENGTH: Final = 120
SUMMARY_MAX_LENGTH: Final = 280
DESCRIPTION_MAX_LENGTH: Final = 10_000
PROTOTYPE_MAX_LENGTH: Final = 200
CATEGORY_NAME_MAX_LENGTH: Final = 60
ALT_TEXT_MAX_LENGTH: Final = 250
GALLERY_MAX_SIZE: Final = 40
# 100 000 €: far above anything this shop sells, low enough to catch a typo.
PRICE_MAX_CENTS: Final = 10_000_000
DIMENSION_MAX_MM: Final = Decimal(10_000)
WEIGHT_MAX_G: Final = 100_000
# A scale's code names it in SKUs and addresses: H0, TT, N, Z, 0, G, 124 (for 1:24).
SCALE_CODE: Final = re.compile(r"[A-Z0-9]{1,4}")
SCALE_NAME_MAX_LENGTH: Final = 20
SCALE_RATIO_MIN: Final = Decimal(1)
SCALE_RATIO_MAX: Final = Decimal(1000)
TRACK_GAUGE_MAX_MM: Final = Decimal("999.9")
# Made to order: how long the workshop needs, as a range of weeks the shop shows.
LEAD_TIME_MAX_WEEKS: Final = 52
DEFAULT_LEAD_TIME_WEEKS: Final = (4, 6)
# GS1 reserves the prefixes 20 to 29 for numbers used inside one company.
INTERNAL_GTIN_PREFIX: Final = "20"
_GTIN_SERIAL_DIGITS: Final = 10


class _Unset(Enum):
    UNSET = auto()


UNSET: Final = _Unset.UNSET
"""Marks a field a partial update leaves as it is (``None`` clears a field)."""

type Maybe[T] = T | Literal[_Unset.UNSET]


class ProductStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    ARCHIVED = "archived"


class MediaRole(StrEnum):
    """What a gallery image shows."""

    GALLERY = "gallery"
    DETAIL = "detail"
    SCALE_COMPARISON = "scale_comparison"


# --- Reference data -------------------------------------------------------------------


@dataclass(eq=False, kw_only=True)
class Scale:
    """A scale such as H0: models at 1:87. Railway models of it run on 16.5 mm track;
    road vehicles have a scale but no track, so the gauge is optional.

    The code is fixed once created: it is part of every SKU and of the shop's addresses.
    """

    code: str
    name: str
    ratio_denominator: Decimal
    track_gauge_mm: Decimal | None

    @classmethod
    def create(
        cls, *, code: str, name: str, ratio_denominator: Decimal, track_gauge_mm: Decimal | None
    ) -> "Scale":
        return cls(
            code=_scale_code(code),
            name=single_line(name, field="name", max_length=SCALE_NAME_MAX_LENGTH),
            ratio_denominator=_ratio(ratio_denominator),
            track_gauge_mm=_track_gauge(track_gauge_mm),
        )

    def change(
        self,
        *,
        name: Maybe[str] = UNSET,
        ratio_denominator: Maybe[Decimal] = UNSET,
        track_gauge_mm: Maybe[Decimal | None] = UNSET,
    ) -> None:
        if name is not UNSET:
            self.name = single_line(name, field="name", max_length=SCALE_NAME_MAX_LENGTH)
        if ratio_denominator is not UNSET:
            self.ratio_denominator = _ratio(ratio_denominator)
        if track_gauge_mm is not UNSET:
            self.track_gauge_mm = _track_gauge(track_gauge_mm)

    @property
    def ratio(self) -> str:
        """``1:87``, ``1:22,5`` - written the German way."""
        number = self.ratio_denominator.normalize()
        text = f"{number:f}".replace(".", ",")
        return f"1:{text}"


def _scale_code(value: str) -> str:
    code = value.strip().upper()
    if not SCALE_CODE.fullmatch(code):
        raise InvalidFieldError("code", "invalid", "one to four letters or digits, e.g. H0")
    return code


def _one_decimal(value: Decimal, *, field: str) -> Decimal:
    if not value.is_finite() or value != value.quantize(Decimal("0.1")):
        raise InvalidFieldError(field, "invalid", "a number with at most one decimal place")
    return value.quantize(Decimal("0.1"))


def _ratio(value: Decimal) -> Decimal:
    ratio = _one_decimal(value, field="ratio_denominator")
    if not SCALE_RATIO_MIN < ratio <= SCALE_RATIO_MAX:
        raise InvalidFieldError("ratio_denominator", "out_of_range", "between 1:1 and 1:1000")
    return ratio


def _track_gauge(value: Decimal | None) -> Decimal | None:
    if value is None:
        return None
    gauge = _one_decimal(value, field="track_gauge_mm")
    if not Decimal(0) < gauge <= TRACK_GAUGE_MAX_MM:
        raise InvalidFieldError("track_gauge_mm", "out_of_range", "above 0 and plausible")
    return gauge


@dataclass(frozen=True, slots=True)
class Finish:
    """How a variant is delivered; its letter ends the SKU."""

    code: str
    name: str
    sku_letter: str
    position: int


@dataclass(frozen=True, slots=True)
class Epoch:
    """A period of German railway history, e.g. Epoche III (1949-1970)."""

    code: str
    name: str
    period: str
    position: int


# --- Numbers --------------------------------------------------------------------------


def ean13_check_digit(first_twelve: str) -> int:
    """GS1 check digit: weights 1 and 3 alternating from the left, then to the next ten."""
    if len(first_twelve) != 12 or not first_twelve.isdigit():  # noqa: PLR2004
        msg = "twelve digits expected"
        raise ValueError(msg)
    total = sum(int(digit) * (3 if index % 2 else 1) for index, digit in enumerate(first_twelve))
    return (10 - total % 10) % 10


def internal_gtin(serial: int) -> str:
    """The EAN-13 for the ``serial``-th variant: prefix 20, ten digits, check digit."""
    if not 0 < serial < 10**_GTIN_SERIAL_DIGITS:
        msg = f"serial {serial} does not fit {_GTIN_SERIAL_DIGITS} digits"
        raise ValueError(msg)
    body = f"{INTERNAL_GTIN_PREFIX}{serial:0{_GTIN_SERIAL_DIGITS}d}"
    return f"{body}{ean13_check_digit(body)}"


def variant_sku(product_number: int, scale_code: str, finish: Finish) -> str:
    """Readable article number, e.g. ``MB-000042-H0-B`` for a painted H0 variant."""
    return f"MB-{product_number:06d}-{scale_code.upper()}-{finish.sku_letter}"


def check_lead_time(lead_time_weeks: tuple[int, int]) -> tuple[int, int]:
    """A range of weeks from 1 to 52, the upper bound not below the lower one."""
    shortest, longest = lead_time_weeks
    if not 1 <= shortest <= LEAD_TIME_MAX_WEEKS:
        raise InvalidFieldError(
            "lead_time_min_weeks", "out_of_range", f"1 to {LEAD_TIME_MAX_WEEKS} weeks"
        )
    if not shortest <= longest <= LEAD_TIME_MAX_WEEKS:
        raise InvalidFieldError(
            "lead_time_max_weeks", "out_of_range", f"the minimum to {LEAD_TIME_MAX_WEEKS} weeks"
        )
    return shortest, longest


def check_price(price_cents: int, compare_at_price_cents: int | None) -> None:
    if not 0 <= price_cents <= PRICE_MAX_CENTS:
        raise InvalidFieldError("price_cents", "out_of_range", "price out of range")
    if compare_at_price_cents is not None and not (
        price_cents < compare_at_price_cents <= PRICE_MAX_CENTS
    ):
        raise InvalidFieldError(
            "compare_at_price_cents", "not_above_price", "must be above the price"
        )


@dataclass(frozen=True, slots=True)
class Dimensions:
    """Size and weight of the model in one scale; any of them may be unknown."""

    length_mm: Decimal | None = None
    width_mm: Decimal | None = None
    height_mm: Decimal | None = None
    weight_g: int | None = None

    def __post_init__(self) -> None:
        for name in ("length_mm", "width_mm", "height_mm"):
            value: Decimal | None = getattr(self, name)
            if value is not None and not Decimal(0) < value <= DIMENSION_MAX_MM:
                raise InvalidFieldError(name, "out_of_range", "must be above 0 and plausible")
        if self.weight_g is not None and not 0 < self.weight_g <= WEIGHT_MAX_G:
            raise InvalidFieldError("weight_g", "out_of_range", "must be above 0 and plausible")


# --- Categories -----------------------------------------------------------------------


@dataclass(eq=False, kw_only=True)
class Category:
    """A shelf of the shop, e.g. Gebäude > Stellwerke. Cycles are refused by the service."""

    id: UUID
    parent_id: UUID | None
    slug: str
    name: str
    position: int
    created_at: datetime
    updated_at: datetime

    @classmethod
    def create(
        cls, *, name: str, slug: str, parent_id: UUID | None, position: int, now: datetime
    ) -> "Category":
        return cls(
            id=new_id(),
            parent_id=parent_id,
            slug=check_slug(slug),
            name=single_line(name, field="name", max_length=CATEGORY_NAME_MAX_LENGTH),
            position=position,
            created_at=now,
            updated_at=now,
        )

    def change(
        self,
        *,
        name: Maybe[str] = UNSET,
        slug: Maybe[str] = UNSET,
        parent_id: Maybe[UUID | None] = UNSET,
        position: Maybe[int] = UNSET,
        now: datetime,
    ) -> None:
        if name is not UNSET:
            self.name = single_line(name, field="name", max_length=CATEGORY_NAME_MAX_LENGTH)
        if slug is not UNSET:
            self.slug = check_slug(slug)
        if parent_id is not UNSET:
            self.parent_id = parent_id
        if position is not UNSET:
            self.position = position
        self.updated_at = now


# --- The product aggregate ------------------------------------------------------------


@dataclass(eq=False, kw_only=True)
class Variant:
    """What a customer buys: one scale in one finish, with SKU, EAN and price.

    A variant is either *in stock* (sold from the shelves, sold out when they are
    empty) or *made to order* (``allow_backorder``: always for sale, made within its
    lead time, a range of weeks).
    """

    id: UUID
    product_scale_id: UUID
    finish_code: str
    sku: str
    gtin: str
    price_cents: int
    compare_at_price_cents: int | None
    allow_backorder: bool
    active: bool
    created_at: datetime
    updated_at: datetime
    lead_time_min_weeks: int | None = None
    lead_time_max_weeks: int | None = None

    @property
    def lead_time_weeks(self) -> tuple[int, int] | None:
        if self.lead_time_min_weeks is None or self.lead_time_max_weeks is None:
            return None
        return self.lead_time_min_weeks, self.lead_time_max_weeks

    def set_lead_time(self, lead_time_weeks: tuple[int, int] | None) -> None:
        """Change the lead time; one made to order gets the default if it has none."""
        if self.allow_backorder and lead_time_weeks is None:
            lead_time_weeks = DEFAULT_LEAD_TIME_WEEKS
        if lead_time_weeks is None:
            self.lead_time_min_weeks = self.lead_time_max_weeks = None
        else:
            self.lead_time_min_weeks, self.lead_time_max_weeks = check_lead_time(lead_time_weeks)


@dataclass(eq=False, kw_only=True)
class ProductScale:
    """The product in one scale, with the model's size in that scale."""

    id: UUID
    product_id: UUID
    scale_code: str
    length_mm: Decimal | None
    width_mm: Decimal | None
    height_mm: Decimal | None
    weight_g: int | None
    variants: list[Variant] = field(default_factory=list)

    def variant_for(self, finish_code: str) -> Variant | None:
        return next((v for v in self.variants if v.finish_code == finish_code), None)


@dataclass(eq=False, kw_only=True)
class ProductEpoch:
    product_id: UUID
    epoch_code: str


@dataclass(eq=False, kw_only=True)
class ProductMedia:
    """An image of the gallery; ``position`` 0 is the main image.

    ``scale_code`` and ``finish_code`` say which scale or finish the photo shows, so
    the shop can switch the gallery with the customer's choice.
    """

    product_id: UUID
    asset_id: UUID
    position: int
    role: MediaRole
    alt_text: str
    scale_code: str | None
    finish_code: str | None


@dataclass(frozen=True, slots=True)
class GalleryEntry:
    """One image of a gallery as an editor sets it (order = position)."""

    asset_id: UUID
    role: MediaRole = MediaRole.GALLERY
    alt_text: str = ""
    scale_code: str | None = None
    finish_code: str | None = None


@dataclass(frozen=True, slots=True)
class VariantDraft:
    """The values of a new variant; SKU and EAN are assigned by the product."""

    finish: Finish
    price_cents: int
    compare_at_price_cents: int | None = None
    allow_backorder: bool = False
    lead_time_weeks: tuple[int, int] | None = None
    """For a variant made to order; without one it gets the default of 4 to 6 weeks."""
    active: bool = True


@dataclass(eq=False, kw_only=True)
class Product:
    """A product of the catalogue. The aggregate root of the catalogue module.

    Rules a product in the shop (``active``) always satisfies, checked on publishing
    and on every later change: it has a category, at least one active variant and a
    main image that is ready. The slug is fixed once the product has been published,
    because links and search engines point to it.
    """

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
    scales: list[ProductScale] = field(default_factory=list)
    epochs: list[ProductEpoch] = field(default_factory=list)
    media: list[ProductMedia] = field(default_factory=list)
    # Maintained by the persistence layer for optimistic locking.
    version: int = 1

    @classmethod
    def create(cls, *, number: int, name: str, slug: str, now: datetime) -> "Product":
        return cls(
            id=new_id(),
            number=number,
            slug=check_slug(slug),
            name=single_line(name, field="name", max_length=PRODUCT_NAME_MAX_LENGTH),
            summary="",
            description="",
            prototype="",
            primary_category_id=None,
            status=ProductStatus.DRAFT,
            published_at=None,
            archived_at=None,
            created_at=now,
            updated_at=now,
        )

    # --- Reading ------------------------------------------------------------------------

    @property
    def is_active(self) -> bool:
        return self.status is ProductStatus.ACTIVE

    @property
    def epoch_codes(self) -> list[str]:
        return [epoch.epoch_code for epoch in self.epochs]

    @property
    def main_image(self) -> ProductMedia | None:
        return min(self.media, key=lambda entry: entry.position, default=None)

    @property
    def gallery(self) -> list[ProductMedia]:
        return sorted(self.media, key=lambda entry: entry.position)

    @property
    def variants(self) -> list[Variant]:
        return [variant for scale in self.scales for variant in scale.variants]

    @property
    def lowest_price_cents(self) -> int | None:
        """The "from" price of the shop: the cheapest active variant."""
        return min((v.price_cents for v in self.variants if v.active), default=None)

    def scale(self, product_scale_id: UUID) -> ProductScale:
        found = next((s for s in self.scales if s.id == product_scale_id), None)
        if found is None:
            raise ProductScaleNotFoundError
        return found

    def scale_with_variant(self, variant_id: UUID) -> tuple[ProductScale, Variant]:
        for scale in self.scales:
            for variant in scale.variants:
                if variant.id == variant_id:
                    return scale, variant
        raise VariantNotFoundError

    def publish_blockers(self, *, main_image_ready: bool) -> list[PublishBlocker]:
        """Everything that keeps the product out of the shop, for a checklist."""
        blockers: list[PublishBlocker] = []
        if self.primary_category_id is None:
            blockers.append(PublishBlocker.NO_CATEGORY)
        if not any(variant.active for variant in self.variants):
            blockers.append(PublishBlocker.NO_ACTIVE_VARIANT)
        if self.main_image is None:
            blockers.append(PublishBlocker.NO_MAIN_IMAGE)
        elif not main_image_ready:
            blockers.append(PublishBlocker.MAIN_IMAGE_NOT_READY)
        return blockers

    # --- Master data ----------------------------------------------------------------------

    def change_details(
        self,
        *,
        name: Maybe[str] = UNSET,
        slug: Maybe[str] = UNSET,
        summary: Maybe[str] = UNSET,
        description: Maybe[str] = UNSET,
        prototype: Maybe[str] = UNSET,
        primary_category_id: Maybe[UUID | None] = UNSET,
        epoch_codes: Maybe[list[str]] = UNSET,
        now: datetime,
    ) -> None:
        """Change the texts, address, category or epochs. Codes are checked by the service."""
        if name is not UNSET:
            self.name = single_line(name, field="name", max_length=PRODUCT_NAME_MAX_LENGTH)
        if slug is not UNSET and slug != self.slug:
            if self.published_at is not None:
                raise SlugLockedError
            self.slug = check_slug(slug)
        if summary is not UNSET:
            self.summary = single_line(
                summary, field="summary", max_length=SUMMARY_MAX_LENGTH, required=False
            )
        if description is not UNSET:
            self.description = multi_line(
                description, field="description", max_length=DESCRIPTION_MAX_LENGTH
            )
        if prototype is not UNSET:
            self.prototype = single_line(
                prototype, field="prototype", max_length=PROTOTYPE_MAX_LENGTH, required=False
            )
        if primary_category_id is not UNSET:
            self.primary_category_id = primary_category_id
        if epoch_codes is not UNSET:
            wanted = list(dict.fromkeys(epoch_codes))
            # Keep the rows of epochs that stay, so nothing is deleted and re-inserted.
            self.epochs = [e for e in self.epochs if e.epoch_code in wanted] + [
                ProductEpoch(product_id=self.id, epoch_code=code)
                for code in wanted
                if code not in self.epoch_codes
            ]
        self._ensure_still_sellable()
        self.updated_at = now

    # --- Scales and variants --------------------------------------------------------------

    def add_scale(self, scale: Scale, dimensions: Dimensions, now: datetime) -> ProductScale:
        if any(s.scale_code == scale.code for s in self.scales):
            raise ScaleAlreadyAddedError
        product_scale = ProductScale(
            id=new_id(),
            product_id=self.id,
            scale_code=scale.code,
            length_mm=dimensions.length_mm,
            width_mm=dimensions.width_mm,
            height_mm=dimensions.height_mm,
            weight_g=dimensions.weight_g,
        )
        self.scales.append(product_scale)
        self.updated_at = now
        return product_scale

    def change_dimensions(
        self, product_scale_id: UUID, dimensions: Dimensions, now: datetime
    ) -> None:
        product_scale = self.scale(product_scale_id)
        product_scale.length_mm = dimensions.length_mm
        product_scale.width_mm = dimensions.width_mm
        product_scale.height_mm = dimensions.height_mm
        product_scale.weight_g = dimensions.weight_g
        self.updated_at = now

    def remove_scale(self, product_scale_id: UUID, now: datetime) -> None:
        """Drop a scale with its variants. Photos tagged with it lose the tag."""
        product_scale = self.scale(product_scale_id)
        self.scales.remove(product_scale)
        for entry in self.media:
            if entry.scale_code == product_scale.scale_code:
                entry.scale_code = None
        self._ensure_still_sellable()
        self.updated_at = now

    def add_variant(
        self, product_scale_id: UUID, draft: VariantDraft, *, gtin: str, now: datetime
    ) -> Variant:
        product_scale = self.scale(product_scale_id)
        if product_scale.variant_for(draft.finish.code) is not None:
            raise VariantAlreadyExistsError
        check_price(draft.price_cents, draft.compare_at_price_cents)
        variant = Variant(
            id=new_id(),
            product_scale_id=product_scale.id,
            finish_code=draft.finish.code,
            sku=variant_sku(self.number, product_scale.scale_code, draft.finish),
            gtin=gtin,
            price_cents=draft.price_cents,
            compare_at_price_cents=draft.compare_at_price_cents,
            allow_backorder=draft.allow_backorder,
            active=draft.active,
            created_at=now,
            updated_at=now,
        )
        variant.set_lead_time(draft.lead_time_weeks)
        product_scale.variants.append(variant)
        self.updated_at = now
        return variant

    def change_variant(
        self,
        variant_id: UUID,
        *,
        price_cents: Maybe[int] = UNSET,
        compare_at_price_cents: Maybe[int | None] = UNSET,
        allow_backorder: Maybe[bool] = UNSET,
        lead_time_weeks: Maybe[tuple[int, int] | None] = UNSET,
        active: Maybe[bool] = UNSET,
        now: datetime,
    ) -> None:
        """Change what is given; a variant made to order always keeps a lead time."""
        _, variant = self.scale_with_variant(variant_id)
        new_price = variant.price_cents if price_cents is UNSET else price_cents
        new_compare = (
            variant.compare_at_price_cents
            if compare_at_price_cents is UNSET
            else compare_at_price_cents
        )
        check_price(new_price, new_compare)
        variant.price_cents = new_price
        variant.compare_at_price_cents = new_compare
        if allow_backorder is not UNSET:
            variant.allow_backorder = allow_backorder
        variant.set_lead_time(
            variant.lead_time_weeks if lead_time_weeks is UNSET else lead_time_weeks
        )
        if active is not UNSET:
            variant.active = active
        variant.updated_at = now
        self._ensure_still_sellable()
        self.updated_at = now

    def remove_variant(self, variant_id: UUID, now: datetime) -> None:
        product_scale, variant = self.scale_with_variant(variant_id)
        product_scale.variants.remove(variant)
        self._ensure_still_sellable()
        self.updated_at = now

    # --- Gallery --------------------------------------------------------------------------

    def attach_image(self, asset_id: UUID, *, alt_text: str, now: datetime) -> ProductMedia:
        """Append an image to the gallery; the first one becomes the main image.

        Attaching an image that is already in the gallery changes nothing.
        """
        existing = next((m for m in self.media if m.asset_id == asset_id), None)
        if existing is not None:
            return existing
        if len(self.media) >= GALLERY_MAX_SIZE:
            raise InvalidFieldError(
                "asset_id", "gallery_full", f"at most {GALLERY_MAX_SIZE} images"
            )
        entry = ProductMedia(
            product_id=self.id,
            asset_id=asset_id,
            position=max((m.position for m in self.media), default=-1) + 1,
            role=MediaRole.GALLERY,
            alt_text=single_line(
                alt_text, field="alt_text", max_length=ALT_TEXT_MAX_LENGTH, required=False
            ),
            scale_code=None,
            finish_code=None,
        )
        self.media.append(entry)
        self.updated_at = now
        return entry

    def arrange_gallery(
        self, entries: list[GalleryEntry], *, main_image_ready: bool, now: datetime
    ) -> None:
        """Set order, roles, alt texts and tags in one step; images left out are removed.

        Only images already in the gallery can be arranged (new ones are attached).
        ``main_image_ready`` tells whether the first entry may be shown in the shop.
        """
        current = {entry.asset_id: entry for entry in self.media}
        seen: set[UUID] = set()
        scale_codes = {s.scale_code for s in self.scales}
        for index, wanted in enumerate(entries):
            if wanted.asset_id in seen:
                raise InvalidFieldError(f"entries.{index}.asset_id", "duplicate", "listed twice")
            if wanted.asset_id not in current:
                raise UnknownReferenceError(f"entries.{index}.asset_id", str(wanted.asset_id))
            if wanted.scale_code is not None and wanted.scale_code not in scale_codes:
                raise UnknownReferenceError(f"entries.{index}.scale_code", wanted.scale_code)
            seen.add(wanted.asset_id)
        arranged: list[ProductMedia] = []
        for index, wanted in enumerate(entries):
            entry = current[wanted.asset_id]
            entry.position = index
            entry.role = wanted.role
            entry.alt_text = single_line(
                wanted.alt_text,
                field=f"entries.{index}.alt_text",
                max_length=ALT_TEXT_MAX_LENGTH,
                required=False,
            )
            entry.scale_code = wanted.scale_code
            entry.finish_code = wanted.finish_code
            arranged.append(entry)
        self.media = arranged
        self._ensure_still_sellable(main_image_ready=main_image_ready)
        self.updated_at = now

    # --- Life cycle -----------------------------------------------------------------------

    def publish(self, *, main_image_ready: bool, now: datetime) -> ProductPublished:
        """Put the product into the shop (again, if it was archived)."""
        if self.is_active:
            raise InvalidProductStateError("the product is already published")
        blockers = self.publish_blockers(main_image_ready=main_image_ready)
        if blockers:
            raise ProductNotPublishableError(blockers)
        self.status = ProductStatus.ACTIVE
        # The first publication stays: "new in the shop" refers to it.
        if self.published_at is None:
            self.published_at = now
        self.archived_at = None
        self.updated_at = now
        return ProductPublished(
            aggregate_id=self.id, occurred_at=now, name=self.name, slug=self.slug
        )

    def archive(self, now: datetime) -> ProductArchived:
        """Take the product out of the shop. It stays for orders and can come back."""
        if not self.is_active:
            raise InvalidProductStateError("only published products can be archived")
        self.status = ProductStatus.ARCHIVED
        self.archived_at = now
        self.updated_at = now
        return ProductArchived(
            aggregate_id=self.id, occurred_at=now, name=self.name, slug=self.slug
        )

    def ensure_deletable(self) -> None:
        """Only drafts that were never in the shop: anything else may have been ordered."""
        if self.status is not ProductStatus.DRAFT or self.published_at is not None:
            raise ProductNotDeletableError

    def change_notice(self, now: datetime) -> ProductUpdated | None:
        """The event announcing a change to a product in the shop; none for drafts."""
        if not self.is_active:
            return None
        return ProductUpdated(aggregate_id=self.id, occurred_at=now, slug=self.slug)

    def _ensure_still_sellable(self, *, main_image_ready: bool = True) -> None:
        """A product in the shop must keep satisfying the rules of :meth:`publish`.

        Only changes to the gallery can affect the main image; the others pass
        ``main_image_ready`` unchanged as true.
        """
        if not self.is_active:
            return
        blockers = self.publish_blockers(main_image_ready=main_image_ready)
        if blockers:
            raise ProductNotPublishableError(blockers)
