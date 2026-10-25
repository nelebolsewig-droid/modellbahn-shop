"""Domain events of the sales module.

Every order event shows up live in the admin area. Payloads carry the order number and
amounts, never the customer's name, e-mail or address: handlers load what they need.
"""

from dataclasses import dataclass
from typing import ClassVar, Final

from modellbahn.platform.events import DomainEvent, JsonObject, domain_event

ORDER_AGGREGATE: Final = "sales.order"
STAFF_AUDIENCE: Final = frozenset({"staff"})


@dataclass(frozen=True, kw_only=True)
class _OrderEvent(DomainEvent):
    # The registry wants event_type and aggregate_type on each event class itself.
    audience: ClassVar[frozenset[str]] = STAFF_AUDIENCE

    number: str
    total_cents: int

    def public_payload(self) -> JsonObject:
        return {
            "order_id": str(self.aggregate_id),
            "number": self.number,
            "total_cents": self.total_cents,
        }


@domain_event
@dataclass(frozen=True, kw_only=True)
class OrderPlaced(_OrderEvent):
    """A customer ordered; the payment is still open."""

    event_type: ClassVar[str] = "sales.order.placed"
    aggregate_type: ClassVar[str] = ORDER_AGGREGATE


@domain_event
@dataclass(frozen=True, kw_only=True)
class OrderPaid(_OrderEvent):
    """The payment of an order came in: the order is binding and can be packed."""

    event_type: ClassVar[str] = "sales.order.paid"
    aggregate_type: ClassVar[str] = ORDER_AGGREGATE


@domain_event
@dataclass(frozen=True, kw_only=True)
class OrderShipped(_OrderEvent):
    """The parcel left the workshop."""

    event_type: ClassVar[str] = "sales.order.shipped"
    aggregate_type: ClassVar[str] = ORDER_AGGREGATE


@domain_event
@dataclass(frozen=True, kw_only=True)
class OrderCancelled(_OrderEvent):
    """The order was cancelled; a payment that had come in was refunded."""

    event_type: ClassVar[str] = "sales.order.cancelled"
    aggregate_type: ClassVar[str] = ORDER_AGGREGATE

    refunded: bool
