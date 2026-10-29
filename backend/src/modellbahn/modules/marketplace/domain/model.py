"""The marketplace model: the shop's eBay account, its offers there, and the orders from there.

The **account** is the one connection to eBay with its settings: the business policies
(payment, returns, shipping) and the location every offer needs, the markup on the shop's
prices for eBay's fees, and how many pieces of a model made to order eBay may sell at once.

A **listing** is a product in one scale as one offer on eBay; each variant (the kit, the
finished model in each colour) is a choice in it. The shop decides what it says: whenever
the catalogue or the stock changes, the listing is due for a sync and rewritten as a
whole. Nobody edits it on eBay.

A **marketplace order** is a paid order as eBay reports it, kept as it came (buyer,
address, lines with eBay's line ids). The sales module turns it into one of its orders;
shipping that order reports the tracking number back to eBay.

Plain dataclasses without any framework, mapped imperatively by the infrastructure.
Every method that depends on time takes ``now``.
"""

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Final
from uuid import UUID

from modellbahn.modules.marketplace.domain.errors import (
    ConnectionStateInvalidError,
    InvalidFieldError,
)
from modellbahn.modules.marketplace.domain.events import (
    ListingChanged,
    MarketplaceOrderCancelled,
    MarketplaceOrderReceived,
)
from modellbahn.platform.events import DomainEvent
from modellbahn.platform.ids import new_id

EBAY: Final = "ebay"
EBAY_MARKETPLACE: Final = "EBAY_DE"
# The shop's one warehouse location on eBay, created from the imprint's address.
LOCATION_KEY: Final = "werkstatt"
MARKUP_MAX_PERCENT: Final = 100
MADE_TO_ORDER_QUANTITY_MAX: Final = 20
DEFAULT_MADE_TO_ORDER_QUANTITY: Final = 3
POLICY_ID_MAX_LENGTH: Final = 40
ERROR_MESSAGE_MAX_LENGTH: Final = 500
# Following eBay's consent page and coming back must not take longer than this.
CONNECT_STATE_LIFETIME: Final = timedelta(minutes=15)
_POLICY_ID: Final = re.compile(r"^[0-9A-Za-z_-]{1,40}$")
_CATEGORY_ID: Final = re.compile(r"^[0-9]{1,10}$")


def _text(value: str, max_length: int) -> str:
    cleaned = " ".join(value.split())
    return cleaned[:max_length]


def check_category_id(value: str, *, field: str = "ebay_category_id") -> str:
    """An eBay category is a number, e.g. 180250; empty means "none chosen"."""
    cleaned = value.strip()
    if cleaned and not _CATEGORY_ID.fullmatch(cleaned):
        raise InvalidFieldError(field, "invalid", "an eBay category number")
    return cleaned


# --- Account --------------------------------------------------------------------------


class ConnectionStatus(StrEnum):
    DISCONNECTED = "disconnected"
    CONNECTED = "connected"
    EXPIRED = "expired"
    """eBay no longer accepts the consent (ran out after 18 months, or withdrawn)."""


class Blocker(StrEnum):
    """What keeps offers from going up on eBay."""

    NOT_CONNECTED = "not_connected"
    NO_FULFILLMENT_POLICY = "no_fulfillment_policy"
    NO_PAYMENT_POLICY = "no_payment_policy"
    NO_RETURN_POLICY = "no_return_policy"
    NO_LOCATION = "no_location"


@dataclass(frozen=True, slots=True)
class Tokens:
    """eBay's access and refresh token, encrypted by the infrastructure before they get here."""

    access_token: str
    access_expires_at: datetime
    refresh_token: str
    refresh_expires_at: datetime


@dataclass(eq=False)
class EbayAccount:
    """The connection to the shop's eBay seller account, and how the shop sells there."""

    channel: str
    status: ConnectionStatus
    seller_name: str
    access_token: str
    access_expires_at: datetime | None
    refresh_token: str
    refresh_expires_at: datetime | None
    connect_state_hash: str | None
    connect_state_expires_at: datetime | None
    fulfillment_policy_id: str
    payment_policy_id: str
    return_policy_id: str
    location_ready: bool
    price_markup_percent: int
    made_to_order_quantity: int
    orders_checked_until: datetime | None
    connected_at: datetime | None
    updated_at: datetime

    @classmethod
    def new(cls, now: datetime) -> "EbayAccount":
        return cls(
            channel=EBAY,
            status=ConnectionStatus.DISCONNECTED,
            seller_name="",
            access_token="",
            access_expires_at=None,
            refresh_token="",
            refresh_expires_at=None,
            connect_state_hash=None,
            connect_state_expires_at=None,
            fulfillment_policy_id="",
            payment_policy_id="",
            return_policy_id="",
            location_ready=False,
            price_markup_percent=0,
            made_to_order_quantity=DEFAULT_MADE_TO_ORDER_QUANTITY,
            orders_checked_until=None,
            connected_at=None,
            updated_at=now,
        )

    @property
    def is_connected(self) -> bool:
        return self.status is ConnectionStatus.CONNECTED

    @property
    def blockers(self) -> list[Blocker]:
        found: list[Blocker] = []
        if not self.is_connected:
            found.append(Blocker.NOT_CONNECTED)
        if not self.fulfillment_policy_id:
            found.append(Blocker.NO_FULFILLMENT_POLICY)
        if not self.payment_policy_id:
            found.append(Blocker.NO_PAYMENT_POLICY)
        if not self.return_policy_id:
            found.append(Blocker.NO_RETURN_POLICY)
        if not self.location_ready:
            found.append(Blocker.NO_LOCATION)
        return found

    def begin_connect(self, state_hash: str, now: datetime) -> None:
        """Remember the state sent to eBay's consent page; only its answer may connect."""
        self.connect_state_hash = state_hash
        self.connect_state_expires_at = now + CONNECT_STATE_LIFETIME
        self.updated_at = now

    def check_state(self, state_hash: str, now: datetime) -> None:
        """The answer belongs to the connection started here, and in time; used once."""
        expected, expires = self.connect_state_hash, self.connect_state_expires_at
        self.connect_state_hash = self.connect_state_expires_at = None
        if expected is None or expires is None or expected != state_hash or now > expires:
            raise ConnectionStateInvalidError

    def connect(self, *, seller_name: str, tokens: Tokens, now: datetime) -> None:
        if self.seller_name and seller_name != self.seller_name:
            # Another eBay account: its policies and location are not ours to reuse.
            self._forget_account_settings()
        self.seller_name = _text(seller_name, 64)
        self._store(tokens)
        self.status = ConnectionStatus.CONNECTED
        self.connected_at = now
        self.updated_at = now

    def renew(self, *, access_token: str, access_expires_at: datetime, now: datetime) -> None:
        """A fresh access token from the refresh token (it lives two hours)."""
        self.access_token = access_token
        self.access_expires_at = access_expires_at
        self.updated_at = now

    def expire(self, now: datetime) -> None:
        """eBay refused the refresh token: the owner has to give consent again."""
        self._clear_tokens()
        self.status = ConnectionStatus.EXPIRED
        self.updated_at = now

    def disconnect(self, now: datetime) -> None:
        self._clear_tokens()
        self._forget_account_settings()
        self.seller_name = ""
        self.status = ConnectionStatus.DISCONNECTED
        self.connected_at = None
        self.updated_at = now

    def change_settings(
        self,
        *,
        fulfillment_policy_id: str | None = None,
        payment_policy_id: str | None = None,
        return_policy_id: str | None = None,
        price_markup_percent: int | None = None,
        made_to_order_quantity: int | None = None,
        now: datetime,
    ) -> None:
        """Change what is given (``None`` keeps it); an empty policy id clears it."""
        if fulfillment_policy_id is not None:
            self.fulfillment_policy_id = _policy(fulfillment_policy_id, "fulfillment_policy_id")
        if payment_policy_id is not None:
            self.payment_policy_id = _policy(payment_policy_id, "payment_policy_id")
        if return_policy_id is not None:
            self.return_policy_id = _policy(return_policy_id, "return_policy_id")
        if price_markup_percent is not None:
            if not 0 <= price_markup_percent <= MARKUP_MAX_PERCENT:
                raise InvalidFieldError(
                    "price_markup_percent", "out_of_range", f"0 to {MARKUP_MAX_PERCENT} percent"
                )
            self.price_markup_percent = price_markup_percent
        if made_to_order_quantity is not None:
            if not 1 <= made_to_order_quantity <= MADE_TO_ORDER_QUANTITY_MAX:
                raise InvalidFieldError(
                    "made_to_order_quantity",
                    "out_of_range",
                    f"1 to {MADE_TO_ORDER_QUANTITY_MAX} pieces",
                )
            self.made_to_order_quantity = made_to_order_quantity
        self.updated_at = now

    def location_created(self, now: datetime) -> None:
        self.location_ready = True
        self.updated_at = now

    def orders_checked(self, until: datetime, now: datetime) -> None:
        """eBay's orders changed before ``until`` are known; the next check starts there."""
        self.orders_checked_until = until
        self.updated_at = now

    def listing_price(self, price_cents: int) -> int:
        """The shop's price with the markup, rounded half up to the cent."""
        return (price_cents * (100 + self.price_markup_percent) + 50) // 100

    def listing_quantity(self, *, free_units: int, made_to_order: bool) -> int:
        """What eBay may sell at once: the pieces on the shelf, at least the made-to-order cap."""
        return max(free_units, self.made_to_order_quantity) if made_to_order else free_units

    def _store(self, tokens: Tokens) -> None:
        self.access_token = tokens.access_token
        self.access_expires_at = tokens.access_expires_at
        self.refresh_token = tokens.refresh_token
        self.refresh_expires_at = tokens.refresh_expires_at

    def _clear_tokens(self) -> None:
        self.access_token = self.refresh_token = ""
        self.access_expires_at = self.refresh_expires_at = None
        self.connect_state_hash = self.connect_state_expires_at = None

    def _forget_account_settings(self) -> None:
        self.fulfillment_policy_id = self.payment_policy_id = self.return_policy_id = ""
        self.location_ready = False


def _policy(value: str, field: str) -> str:
    cleaned = value.strip()
    if cleaned and not _POLICY_ID.fullmatch(cleaned):
        raise InvalidFieldError(field, "invalid", "an eBay policy id")
    return cleaned


# --- Listings -------------------------------------------------------------------------


class ListingStatus(StrEnum):
    PENDING = "pending"
    """Wanted on eBay, not up yet."""
    ACTIVE = "active"
    FAILED = "failed"
    """eBay refused the last sync; the error says why. An earlier version may still be up."""
    ENDED = "ended"


@dataclass(eq=False)
class ListingItem:
    """One variant as a choice of the listing, with what eBay was last told."""

    listing_id: UUID
    sku: str
    variant_id: UUID
    offer_id: str
    quantity: int
    price_cents: int


@dataclass(eq=False)
class Listing:
    """A product in one scale as an offer on eBay."""

    id: UUID
    product_id: UUID
    scale_code: str
    group_key: str
    """eBay's key of the offer with its choices: ``MB-000042-H0``."""
    wanted: bool
    status: ListingStatus
    external_id: str
    """eBay's listing number, once the offer went up (``ebay.de/itm/<number>``)."""
    needs_sync: bool
    error_code: str | None
    error_message: str
    synced_at: datetime | None
    created_at: datetime
    updated_at: datetime
    items: list[ListingItem] = field(default_factory=list)

    @classmethod
    def create(
        cls, *, product_id: UUID, scale_code: str, group_key: str, now: datetime
    ) -> "Listing":
        return cls(
            id=new_id(),
            product_id=product_id,
            scale_code=scale_code,
            group_key=group_key,
            wanted=True,
            status=ListingStatus.PENDING,
            external_id="",
            needs_sync=True,
            error_code=None,
            error_message="",
            synced_at=None,
            created_at=now,
            updated_at=now,
        )

    @property
    def offer_ids(self) -> dict[str, str]:
        return {item.sku: item.offer_id for item in self.items if item.offer_id}

    @property
    def is_up(self) -> bool:
        """eBay shows (a version of) it: it went up and has not been ended since."""
        return bool(self.external_id) and self.status is not ListingStatus.ENDED

    def want(self, wanted: bool, now: datetime) -> None:
        """Offer it on eBay, or take it down; the next sync does it."""
        self.wanted = wanted
        if wanted and self.status is ListingStatus.ENDED:
            self.status = ListingStatus.PENDING
        self.request_sync(now)

    def request_sync(self, now: datetime) -> None:
        self.needs_sync = True
        self.updated_at = now

    def synced(
        self, *, external_id: str, items: list[ListingItem], now: datetime
    ) -> ListingChanged:
        self.external_id = external_id
        self.items = items
        self.status = ListingStatus.ACTIVE
        return self._settled(now)

    def ended(self, now: datetime, *, items: list[ListingItem] | None = None) -> ListingChanged:
        """Off eBay: no longer wanted, or (still wanted) nothing left to sell for now.

        ``items`` are the choices it would have: a stock change of one brings it back.
        """
        self.status = ListingStatus.ENDED
        if items is not None:
            self.items = items
        return self._settled(now)

    def held_back(self, *, code: str, message: str, now: datetime) -> ListingChanged:
        """The shop keeps it off eBay (no photo, no category, not in the shop): ended there."""
        self.external_id = ""
        return self.failed(code=code, message=message, now=now)

    def failed(self, *, code: str, message: str, now: datetime) -> ListingChanged:
        """eBay refused the sync; a version from before may still be up."""
        self.status = ListingStatus.FAILED
        self.needs_sync = False
        self.error_code = code
        self.error_message = _text(message, ERROR_MESSAGE_MAX_LENGTH)
        self.synced_at = now
        self.updated_at = now
        return self._changed(now)

    def _settled(self, now: datetime) -> ListingChanged:
        self.needs_sync = False
        self.error_code = None
        self.error_message = ""
        self.synced_at = now
        self.updated_at = now
        return self._changed(now)

    def _changed(self, now: datetime) -> ListingChanged:
        return ListingChanged(
            aggregate_id=self.id,
            occurred_at=now,
            product_id=self.product_id,
            scale_code=self.scale_code,
            status=self.status.value,
        )


# --- Orders ---------------------------------------------------------------------------


class MarketplaceOrderStatus(StrEnum):
    RECEIVED = "received"
    """Handed to the sales module, which made it one of its orders."""
    REJECTED = "rejected"
    """Could not become an order (an unknown article, an address the shop cannot serve)."""
    SHIPPED = "shipped"
    """The tracking number went back to eBay."""
    CANCELLED = "cancelled"


@dataclass(frozen=True, slots=True)
class ReceivedLine:
    """A line of an order as eBay reports it, matched to a variant if the article is ours."""

    line_ref: str
    sku: str
    variant_id: UUID | None
    title: str
    quantity: int
    unit_price_cents: int


@dataclass(eq=False)
class MarketplaceOrderLine:
    id: UUID
    marketplace_order_id: UUID
    position: int
    line_ref: str
    """eBay's id of the line; shipping reports it back."""
    sku: str
    variant_id: UUID | None
    title: str
    quantity: int
    unit_price_cents: int


@dataclass(eq=False)
class MarketplaceOrder:
    id: UUID
    channel: str
    external_id: str
    order_id: UUID
    """The sales order this becomes (its id is chosen here, so both sides can find it)."""
    status: MarketplaceOrderStatus
    buyer_name: str
    email: str
    recipient: str
    street: str
    postal_code: str
    city: str
    country_code: str
    shipping_cents: int
    total_cents: int
    paid_at: datetime
    problem: str
    """Why it was rejected, or why reporting the shipment failed; empty when all is well."""
    received_at: datetime
    updated_at: datetime
    shipped_reported_at: datetime | None = None
    lines: list[MarketplaceOrderLine] = field(default_factory=list)

    @classmethod
    def receive(
        cls,
        *,
        channel: str,
        external_id: str,
        buyer_name: str,
        email: str,
        recipient: str,
        street: str,
        postal_code: str,
        city: str,
        country_code: str,
        shipping_cents: int,
        paid_at: datetime,
        lines: list[ReceivedLine],
        problem: str,
        now: datetime,
    ) -> tuple["MarketplaceOrder", list[DomainEvent]]:
        """Keep the order; without a problem the sales module is told to take it over."""
        order_id = new_id()
        marketplace_order_id = new_id()
        order_lines = [
            MarketplaceOrderLine(
                id=new_id(),
                marketplace_order_id=marketplace_order_id,
                position=position,
                line_ref=line.line_ref,
                sku=line.sku,
                variant_id=line.variant_id,
                title=_text(line.title, 200),
                quantity=line.quantity,
                unit_price_cents=line.unit_price_cents,
            )
            for position, line in enumerate(lines)
        ]
        if not problem and any(line.variant_id is None for line in order_lines):
            problem = "unknown article"
        subtotal = sum(line.unit_price_cents * line.quantity for line in order_lines)
        order = cls(
            id=marketplace_order_id,
            channel=channel,
            external_id=external_id,
            order_id=order_id,
            status=MarketplaceOrderStatus.REJECTED if problem else MarketplaceOrderStatus.RECEIVED,
            buyer_name=_text(buyer_name, 80),
            email=email.strip(),
            recipient=_text(recipient, 80),
            street=_text(street, 100),
            postal_code=_text(postal_code, 16),
            city=_text(city, 60),
            country_code=country_code.strip().upper()[:2],
            shipping_cents=shipping_cents,
            total_cents=subtotal + shipping_cents,
            paid_at=paid_at,
            problem=_text(problem, ERROR_MESSAGE_MAX_LENGTH),
            received_at=now,
            updated_at=now,
            lines=order_lines,
        )
        if order.status is MarketplaceOrderStatus.REJECTED:
            return order, []
        return order, [
            MarketplaceOrderReceived(
                aggregate_id=order.id,
                occurred_at=now,
                order_id=order.order_id,
                channel=channel,
                external_id=external_id,
            )
        ]

    def cancel(self, now: datetime) -> list[DomainEvent]:
        """eBay reports the order cancelled; an order the shop already sent stays as it is."""
        if self.status in {MarketplaceOrderStatus.SHIPPED, MarketplaceOrderStatus.CANCELLED}:
            return []
        handed_over = self.status is MarketplaceOrderStatus.RECEIVED
        self.status = MarketplaceOrderStatus.CANCELLED
        self.updated_at = now
        if not handed_over:
            return []
        return [
            MarketplaceOrderCancelled(
                aggregate_id=self.id,
                occurred_at=now,
                order_id=self.order_id,
                channel=self.channel,
                external_id=self.external_id,
            )
        ]

    def shipment_reported(self, now: datetime) -> None:
        self.status = MarketplaceOrderStatus.SHIPPED
        self.problem = ""
        self.shipped_reported_at = now
        self.updated_at = now

    def shipment_failed(self, message: str, now: datetime) -> None:
        self.problem = _text(message, ERROR_MESSAGE_MAX_LENGTH)
        self.updated_at = now
