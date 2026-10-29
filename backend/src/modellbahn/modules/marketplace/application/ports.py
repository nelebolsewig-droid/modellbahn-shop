"""What the marketplace's use cases need from the outside: eBay, the other modules, storage.

eBay sits behind an anti-corruption layer (KONZEPT §2.6): the gateway speaks eBay's REST
APIs and hands back the plain types below. The built-in test marketplace implements the
same port, so the whole flow runs without eBay's keys.
"""

from collections.abc import Callable, Collection, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from types import TracebackType
from typing import Protocol, Self
from uuid import UUID

from modellbahn.modules.catalog.contracts.listings import CategoryLabel, ListingSource, ProductLabel
from modellbahn.modules.catalog.contracts.variants import SaleVariant
from modellbahn.modules.marketplace.domain.model import (
    EbayAccount,
    Listing,
    MarketplaceOrder,
)
from modellbahn.modules.sales.contracts.orders import Shipment
from modellbahn.platform.events import DomainEvent

# --- eBay -----------------------------------------------------------------------------


class GatewayMode(StrEnum):
    TEST = "test"
    """The built-in test marketplace: no keys, nothing leaves the server."""
    SANDBOX = "sandbox"
    PRODUCTION = "production"


class MarketplaceUnavailableError(Exception):
    """eBay could not be reached or asked to wait (5xx, 429, network); try again later."""


class AccessTokenRejectedError(MarketplaceUnavailableError):
    """eBay refused the access token before it ran out; a fresh one may work."""


class MarketplaceRejectedError(Exception):
    """eBay refused the request; ``message`` says why, in eBay's words."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


class AuthorizationRevokedError(Exception):
    """eBay no longer accepts the refresh token: the owner has to give consent again."""


@dataclass(frozen=True, slots=True)
class TokenGrant:
    access_token: str
    access_expires_at: datetime
    refresh_token: str
    refresh_expires_at: datetime


@dataclass(frozen=True, slots=True)
class AccessGrant:
    access_token: str
    access_expires_at: datetime


@dataclass(frozen=True, slots=True)
class PolicyOption:
    id: str
    name: str


@dataclass(frozen=True, slots=True)
class Policies:
    """The business policies of the seller account, to choose from."""

    fulfillment: Sequence[PolicyOption]
    payment: Sequence[PolicyOption]
    returns: Sequence[PolicyOption]


@dataclass(frozen=True, slots=True)
class LocationAddress:
    """Where the parcels leave from: the imprint's address."""

    name: str
    street: str
    postal_code: str
    city: str
    country_code: str


@dataclass(frozen=True, slots=True)
class OfferDraft:
    """One variant as a choice of the listing."""

    sku: str
    quantity: int
    price_cents: int
    aspects: dict[str, list[str]]
    """What sets this choice apart, e.g. ``{"Ausführung": ["Fertigmodell"], "Farbe": ["Gelb"]}``."""
    image_urls: Sequence[str]


@dataclass(frozen=True, slots=True)
class ListingDraft:
    """Everything eBay is told about a product in one scale."""

    group_key: str
    title: str
    description_html: str
    category_id: str
    aspects: dict[str, list[str]]
    image_urls: Sequence[str]
    offers: Sequence[OfferDraft]
    varies_by: Sequence[str]
    """The aspect names the choices differ in (empty for a single choice)."""
    fulfillment_policy_id: str
    payment_policy_id: str
    return_policy_id: str
    location_key: str
    known_offer_ids: dict[str, str] = field(default_factory=dict)
    """Offers eBay already knows from earlier syncs, by SKU."""
    previous_external_id: str = ""
    previous_skus: Sequence[str] = ()
    """What went up last time: a change between one and several choices needs a new listing."""


@dataclass(frozen=True, slots=True)
class PublishedListing:
    external_id: str
    offer_ids: dict[str, str]


@dataclass(frozen=True, slots=True)
class ExternalLine:
    line_ref: str
    sku: str
    title: str
    quantity: int
    unit_price_cents: int


@dataclass(frozen=True, slots=True)
class ExternalOrder:
    """An order as eBay reports it."""

    external_id: str
    buyer_name: str
    email: str
    recipient: str
    street: str
    postal_code: str
    city: str
    country_code: str
    shipping_cents: int
    paid: bool
    cancelled: bool
    paid_at: datetime | None
    lines: Sequence[ExternalLine]


@dataclass(frozen=True, slots=True)
class ShipmentReport:
    external_id: str
    lines: Sequence[tuple[str, int]]
    """eBay's line ids with the quantity shipped."""
    carrier: str
    tracking_number: str
    shipped_at: datetime


class EbayGateway(Protocol):
    """eBay's Sell APIs (Inventory, Fulfillment, Account) and OAuth, or the test marketplace.

    Every call raises :class:`MarketplaceUnavailableError` when eBay cannot be reached and
    :class:`MarketplaceRejectedError` when it refuses the request.
    """

    @property
    def mode(self) -> GatewayMode: ...

    def authorize_url(self, state: str) -> str:
        """eBay's consent page; it sends the owner back to the callback with ``state``."""
        ...

    async def exchange_code(self, code: str) -> TokenGrant: ...

    async def refresh(self, refresh_token: str) -> AccessGrant:
        """A new access token; :class:`AuthorizationRevokedError` if consent is gone."""
        ...

    async def seller_name(self, access_token: str) -> str: ...

    async def policies(self, access_token: str) -> Policies: ...

    async def ensure_location(
        self, access_token: str, key: str, address: LocationAddress
    ) -> None: ...

    async def publish(self, access_token: str, draft: ListingDraft) -> PublishedListing:
        """Create or rewrite the listing as a whole and put it online."""
        ...

    async def end(self, access_token: str, *, group_key: str, offer_ids: dict[str, str]) -> None:
        """Take the listing offline (its offers stay known to eBay for a later return)."""
        ...

    async def orders(
        self, access_token: str, *, modified_since: datetime, until: datetime
    ) -> list[ExternalOrder]:
        """Orders created or changed (paid, cancelled) in the period."""
        ...

    async def report_shipment(self, access_token: str, report: ShipmentReport) -> None: ...

    async def aclose(self) -> None:
        """Release the connections (at shutdown)."""
        ...


class TokenCipher(Protocol):
    """Encrypts eBay's tokens for the database (they open the seller account)."""

    def encrypt(self, plain: str) -> str: ...

    def decrypt(self, sealed: str) -> str: ...


class TestMarketplace(Protocol):
    """Sales on the built-in test marketplace, as a buyer on eBay would make them."""

    async def sell(
        self, *, sku: str, quantity: int, unit_price_cents: int, shipping_cents: int, now: datetime
    ) -> str:
        """Record a paid sale; its order number on the test marketplace."""
        ...

    async def cancel(self, external_id: str, now: datetime) -> bool:
        """Cancel a test sale as a buyer would; False if there is no such sale."""
        ...


# --- Other modules --------------------------------------------------------------------


class Catalog(Protocol):
    """What the marketplace may ask the catalogue."""

    async def listing_source(self, product_id: UUID, scale_code: str) -> ListingSource | None: ...

    async def variants_by_sku(self, skus: Collection[str]) -> dict[str, SaleVariant]: ...

    async def product_labels(self, product_ids: Collection[UUID]) -> dict[UUID, ProductLabel]: ...

    async def categories(self) -> list[CategoryLabel]: ...


class Inventory(Protocol):
    async def free_units(self, variant_ids: Collection[UUID]) -> dict[UUID, int]: ...


class Images(Protocol):
    async def public_urls(self, asset_ids: Sequence[UUID]) -> dict[UUID, str]:
        """The largest web size of each ready image as an absolute URL, in the given order."""
        ...


class Sales(Protocol):
    async def shipment(self, order_id: UUID) -> Shipment | None:
        """How the order was sent, once it was."""
        ...

    async def order_numbers(self, order_ids: Collection[UUID]) -> dict[UUID, str]:
        """The shop's numbers of the orders that exist (an order is made after receipt)."""
        ...

    def address_problem(
        self, *, recipient: str, street: str, postal_code: str, city: str, country_code: str
    ) -> str | None:
        """Why the shop cannot ship there (an unknown country, a broken postal code)."""
        ...


# --- Storage --------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ListingCursor:
    updated_at: datetime
    id: UUID


class AccountRepository(Protocol):
    async def get(self, *, for_update: bool = False) -> EbayAccount | None: ...

    def add(self, account: EbayAccount) -> None: ...


class CategoryMapRepository(Protocol):
    async def all(self) -> dict[UUID, str]:
        """eBay's category number by the catalogue's category id."""
        ...

    async def replace(self, mapping: dict[UUID, str], now: datetime) -> None: ...


class ListingRepository(Protocol):
    async def get(self, listing_id: UUID, *, for_update: bool = False) -> Listing | None: ...

    async def find(
        self, product_id: UUID, scale_code: str, *, for_update: bool = False
    ) -> Listing | None: ...

    async def of_product(self, product_id: UUID) -> list[Listing]: ...

    async def page(self, *, after: ListingCursor | None, limit: int) -> list[Listing]:
        """Listings by last change, newest first."""
        ...

    async def due(self, limit: int) -> list[UUID]:
        """Listings that need a sync, oldest change first, skipping rows others hold."""
        ...

    async def mark_due_for_product(self, product_id: UUID, now: datetime) -> int: ...

    async def mark_due_for_variants(self, variant_ids: Collection[UUID], now: datetime) -> int: ...

    async def mark_all_due(self, now: datetime) -> int:
        """Every wanted or online listing: the settings that shape them all changed."""
        ...

    async def up(self) -> list[Listing]:
        """The listings eBay shows."""
        ...

    async def item_for_sku(self, sku: str) -> tuple[Listing, int] | None:
        """The online listing offering ``sku``, with the price eBay was last told."""
        ...

    def add(self, listing: Listing) -> None: ...


class MarketplaceOrderRepository(Protocol):
    async def get(
        self, marketplace_order_id: UUID, *, for_update: bool = False
    ) -> MarketplaceOrder | None: ...

    async def by_external(
        self, channel: str, external_id: str, *, for_update: bool = False
    ) -> MarketplaceOrder | None: ...

    async def by_order_id(
        self, order_id: UUID, *, for_update: bool = False
    ) -> MarketplaceOrder | None: ...

    async def recent(self, limit: int) -> list[MarketplaceOrder]: ...

    def add(self, order: MarketplaceOrder) -> None: ...


class MarketplaceUnitOfWork(Protocol):
    """One transaction over the marketplace's repositories (see ``platform.uow``)."""

    @property
    def account(self) -> AccountRepository: ...

    @property
    def categories(self) -> CategoryMapRepository: ...

    @property
    def listings(self) -> ListingRepository: ...

    @property
    def orders(self) -> MarketplaceOrderRepository: ...

    @property
    def test_marketplace(self) -> TestMarketplace: ...

    @property
    def catalog(self) -> Catalog: ...

    @property
    def inventory(self) -> Inventory: ...

    @property
    def images(self) -> Images: ...

    @property
    def sales(self) -> Sales: ...

    async def __aenter__(self) -> Self: ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...

    def publish(self, *events: DomainEvent) -> None: ...

    async def commit(self) -> None: ...


type UnitOfWorkFactory = Callable[[], MarketplaceUnitOfWork]
