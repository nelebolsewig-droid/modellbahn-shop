"""Domain events of the sales module.

Every order event and every withdrawal shows up live in the admin area. Payloads carry the
order number and amounts, never the customer's name, e-mail or address: handlers load what
they need.
"""

from dataclasses import dataclass
from typing import ClassVar, Final
from uuid import UUID

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


@domain_event
@dataclass(frozen=True, kw_only=True)
class OrderRefunded(_OrderEvent):
    """Money went back for a paid or shipped order, e.g. after a return (ADR 0020)."""

    event_type: ClassVar[str] = "sales.order.refunded"
    aggregate_type: ClassVar[str] = ORDER_AGGREGATE

    amount_cents: int
    refunded_cents: int
    """Everything refunded for the order so far, this amount included."""


WITHDRAWAL_AGGREGATE: Final = "sales.withdrawal"


@domain_event
@dataclass(frozen=True, kw_only=True)
class WithdrawalReceived(DomainEvent):
    """A consumer withdrew from a contract with the shop's withdrawal function (§ 356a BGB).

    The confirmation of receipt goes out with this event; staff see it live. The payload
    names the order only when number and e-mail address fit one, and never the person.
    """

    event_type: ClassVar[str] = "sales.withdrawal.received"
    aggregate_type: ClassVar[str] = WITHDRAWAL_AGGREGATE
    audience: ClassVar[frozenset[str]] = STAFF_AUDIENCE

    order_id: UUID | None
    number: str | None

    def public_payload(self) -> JsonObject:
        return {
            "withdrawal_id": str(self.aggregate_id),
            "order_id": str(self.order_id) if self.order_id is not None else None,
            "number": self.number,
        }
