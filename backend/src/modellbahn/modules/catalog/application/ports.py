"""What the catalogue use cases need from the outside world, as protocols.

The infrastructure layer implements them; tests may substitute their own.
"""

from collections.abc import Collection
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from types import TracebackType
from typing import Protocol, Self
from uuid import UUID

from modellbahn.modules.catalog.domain.model import (
    Category,
    Epoch,
    Finish,
    Product,
    ProductStatus,
    Scale,
)
from modellbahn.modules.media.contracts.images import ImageView
from modellbahn.platform.events import DomainEvent


class ProductOrder(StrEnum):
    """``created``: newest first, for the admin list; ``published``: newest in the shop.

    The shop also sorts by the lowest price of the active variants and by name.
    """

    CREATED = "created"
    PUBLISHED = "published"
    PRICE_ASC = "price_asc"
    PRICE_DESC = "price_desc"
    NAME = "name"


@dataclass(frozen=True, slots=True)
class ProductCursor:
    """Keyset position: the sort value and id of the last product of the previous page."""

    id: UUID
    published_at: datetime | None = None
    price_cents: int | None = None
    name: str | None = None


@dataclass(frozen=True, slots=True)
class ProductQuery:
    order: ProductOrder
    limit: int
    statuses: frozenset[ProductStatus] | None = None
    category_ids: frozenset[UUID] | None = None
    scale_code: str | None = None
    epoch_code: str | None = None
    text: str | None = None
    after: ProductCursor | None = None


@dataclass(frozen=True, slots=True)
class Article:
    """One variant as a till or a spreadsheet lists it: a line of the article list."""

    product_name: str
    product_status: str
    category_name: str | None
    scale_name: str
    finish_name: str
    color: str
    sku: str
    gtin: str
    price_cents: int
    active: bool
    allow_backorder: bool
    lead_time_weeks: tuple[int, int] | None


class ProductRepository(Protocol):
    async def get(self, product_id: UUID, *, for_update: bool = False) -> Product | None:
        """The product with scales, variants, epochs and gallery. ``for_update`` locks it."""
        ...

    async def get_by_slug(self, slug: str) -> Product | None: ...

    async def get_for_scale(
        self, product_scale_id: UUID, *, for_update: bool = False
    ) -> Product | None:
        """The product a scale row belongs to."""
        ...

    async def get_for_variant(
        self, variant_id: UUID, *, for_update: bool = False
    ) -> Product | None: ...

    async def slug_taken(self, slug: str, *, except_id: UUID | None = None) -> bool: ...

    async def next_number(self) -> int:
        """The next readable product number (a sequence: gaps are possible)."""
        ...

    async def next_gtin_serial(self) -> int: ...

    def add(self, product: Product) -> None: ...

    def mark_changed(self, product: Product) -> None:
        """Count a change in the product's version, even if only a scale or image changed."""
        ...

    async def delete(self, product: Product) -> None: ...

    async def articles(self) -> list[Article]:
        """Every variant of every product that is not archived, by product name."""
        ...

    async def offered_counts(self) -> dict[tuple[UUID, str], int]:
        """Products in the shop per category and scale.

        A product counts in a scale when it has an active variant there, as in
        :meth:`search`, and in its own category only (not in the parents).
        """
        ...

    async def search(self, query: ProductQuery) -> list[Product]:
        """Products matching ``query``, one page in the requested order."""
        ...


class CategoryRepository(Protocol):
    async def all(self) -> list[Category]: ...

    async def get(self, category_id: UUID, *, for_update: bool = False) -> Category | None: ...

    async def get_by_slug(self, slug: str) -> Category | None: ...

    async def slug_taken(self, slug: str, *, except_id: UUID | None = None) -> bool: ...

    def add(self, category: Category) -> None: ...


class ReferenceData(Protocol):
    """Scales, finishes and epochs. Staff maintain the scales; the rest is fixed."""

    async def scales(self) -> list[Scale]:
        """By size of the models: the smallest scale (largest ratio) first."""
        ...

    async def get_scale(self, code: str, *, for_update: bool = False) -> Scale | None: ...

    async def scale_taken(
        self, *, code: str | None = None, name: str | None = None, except_code: str | None = None
    ) -> bool:
        """Whether a scale (other than ``except_code``) has this code or this name."""
        ...

    async def scale_usage(self) -> dict[str, int]:
        """How many products (in any state) are offered in each scale that has any."""
        ...

    async def scale_in_use(self, code: str) -> bool:
        """A product is offered in it or a photo is tagged with it."""
        ...

    def add_scale(self, scale: Scale) -> None: ...

    async def delete_scale(self, scale: Scale) -> None: ...

    async def finishes(self) -> list[Finish]: ...

    async def epochs(self) -> list[Epoch]: ...


class Images(Protocol):
    """The images of the media module, as far as galleries need them."""

    async def load(self, asset_ids: Collection[UUID]) -> dict[UUID, ImageView]:
        """Images among ``asset_ids`` with state and URLs; others are left out."""
        ...


class CatalogUnitOfWork(Protocol):
    """One transaction over the catalogue repositories (see ``platform.uow``)."""

    @property
    def products(self) -> ProductRepository: ...

    @property
    def categories(self) -> CategoryRepository: ...

    @property
    def references(self) -> ReferenceData: ...

    @property
    def images(self) -> Images: ...

    async def __aenter__(self) -> Self: ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...

    def publish(self, *events: DomainEvent) -> None: ...

    async def flush(self) -> None: ...

    async def commit(self) -> None: ...
