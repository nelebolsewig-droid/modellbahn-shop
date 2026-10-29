"""Domain events of the marketplace module.

The payloads carry ids and numbers, never a buyer's name or address: a handler loads what
it needs (the sales module reads a received order through this module's contract).
"""

from dataclasses import dataclass
from typing import ClassVar, Final
from uuid import UUID

from modellbahn.platform.events import DomainEvent, JsonObject, domain_event

ORDER_AGGREGATE: Final = "marketplace.order"
LISTING_AGGREGATE: Final = "marketplace.listing"
STAFF_AUDIENCE: Final = frozenset({"staff"})


@domain_event
@dataclass(frozen=True, kw_only=True)
class MarketplaceOrderReceived(DomainEvent):
    """A paid order came in from eBay; the sales module turns it into one of its orders."""

    event_type: ClassVar[str] = "marketplace.order.received"
    aggregate_type: ClassVar[str] = ORDER_AGGREGATE
    audience: ClassVar[frozenset[str]] = STAFF_AUDIENCE

    order_id: UUID
    channel: str
    external_id: str

    def public_payload(self) -> JsonObject:
        return {
            "marketplace_order_id": str(self.aggregate_id),
            "order_id": str(self.order_id),
            "channel": self.channel,
            "external_id": self.external_id,
        }


@domain_event
@dataclass(frozen=True, kw_only=True)
class MarketplaceOrderCancelled(DomainEvent):
    """The buyer or eBay cancelled an order before it was shipped; the shop follows."""

    event_type: ClassVar[str] = "marketplace.order.cancelled"
    aggregate_type: ClassVar[str] = ORDER_AGGREGATE
    audience: ClassVar[frozenset[str]] = STAFF_AUDIENCE

    order_id: UUID
    channel: str
    external_id: str

    def public_payload(self) -> JsonObject:
        return {
            "marketplace_order_id": str(self.aggregate_id),
            "order_id": str(self.order_id),
            "channel": self.channel,
            "external_id": self.external_id,
        }


@domain_event
@dataclass(frozen=True, kw_only=True)
class ListingChanged(DomainEvent):
    """An offer on eBay went up, changed, failed or ended; the admin area refreshes."""

    event_type: ClassVar[str] = "marketplace.listing.changed"
    aggregate_type: ClassVar[str] = LISTING_AGGREGATE
    audience: ClassVar[frozenset[str]] = STAFF_AUDIENCE

    product_id: UUID
    scale_code: str
    status: str

    def public_payload(self) -> JsonObject:
        return {
            "listing_id": str(self.aggregate_id),
            "product_id": str(self.product_id),
            "scale_code": self.scale_code,
            "status": self.status,
        }
