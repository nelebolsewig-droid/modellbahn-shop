"""Domain events of the inventory module.

Every change of stock shows up live in the admin area: the stock figures, a location's
contents and the pick list of an order refresh without reloading. The payloads carry
codes and ids, nothing personal.
"""

from dataclasses import dataclass
from typing import ClassVar, Final
from uuid import UUID

from modellbahn.platform.events import DomainEvent, JsonObject, domain_event

UNIT_AGGREGATE: Final = "inventory.unit"
LOCATION_AGGREGATE: Final = "inventory.location"
ALLOCATION_AGGREGATE: Final = "inventory.allocation"
PART_AGGREGATE: Final = "inventory.part"
PRINT_JOB_RECEIPT_AGGREGATE: Final = "inventory.print_job_receipt"
STAFF_AUDIENCE: Final = frozenset({"staff"})


@domain_event
@dataclass(frozen=True, kw_only=True)
class StockChanged(DomainEvent):
    """A unit changed its state or place (labelled, put away, picked, shipped …)."""

    event_type: ClassVar[str] = "inventory.stock.changed"
    aggregate_type: ClassVar[str] = UNIT_AGGREGATE
    audience: ClassVar[frozenset[str]] = STAFF_AUDIENCE

    unit_code: str
    variant_id: UUID
    reason: str
    status: str
    location_code: str | None
    previous_location_code: str | None
    order_id: UUID | None

    def public_payload(self) -> JsonObject:
        return {
            "unit_id": str(self.aggregate_id),
            "unit_code": self.unit_code,
            "variant_id": str(self.variant_id),
            "reason": self.reason,
            "status": self.status,
            "location_code": self.location_code,
            "previous_location_code": self.previous_location_code,
            "order_id": str(self.order_id) if self.order_id else None,
        }


@domain_event
@dataclass(frozen=True, kw_only=True)
class AllocationBackordered(DomainEvent):
    """A paid piece has no unit in stock: it has to be made (planning will pick this up)."""

    event_type: ClassVar[str] = "inventory.allocation.backordered"
    aggregate_type: ClassVar[str] = ALLOCATION_AGGREGATE
    audience: ClassVar[frozenset[str]] = STAFF_AUDIENCE

    order_id: UUID
    variant_id: UUID

    def public_payload(self) -> JsonObject:
        return {
            "allocation_id": str(self.aggregate_id),
            "order_id": str(self.order_id),
            "variant_id": str(self.variant_id),
        }


@domain_event
@dataclass(frozen=True, kw_only=True)
class LocationChanged(DomainEvent):
    """A location was created, renamed or removed; open location trees refresh."""

    event_type: ClassVar[str] = "inventory.location.changed"
    aggregate_type: ClassVar[str] = LOCATION_AGGREGATE
    audience: ClassVar[frozenset[str]] = STAFF_AUDIENCE

    code: str
    change: str
    """``created``, ``renamed`` or ``removed``."""

    def public_payload(self) -> JsonObject:
        return {"location_id": str(self.aggregate_id), "code": self.code, "change": self.change}


@domain_event
@dataclass(frozen=True, kw_only=True)
class PartStockChanged(DomainEvent):
    """Parts went into a location, out of it, or into a unit; the aggregate is the part."""

    event_type: ClassVar[str] = "inventory.part_stock.changed"
    aggregate_type: ClassVar[str] = PART_AGGREGATE
    audience: ClassVar[frozenset[str]] = STAFF_AUDIENCE

    part_number: str
    reason: str
    quantity: int
    location_code: str | None
    previous_location_code: str | None

    def public_payload(self) -> JsonObject:
        return {
            "part_id": str(self.aggregate_id),
            "part_number": self.part_number,
            "reason": self.reason,
            "quantity": self.quantity,
            "location_code": self.location_code,
            "previous_location_code": self.previous_location_code,
        }


@domain_event
@dataclass(frozen=True, kw_only=True)
class PartsArrived(DomainEvent):
    """The good parts of a finished plate wait in the receiving area; the aggregate is the job."""

    event_type: ClassVar[str] = "inventory.parts.arrived"
    aggregate_type: ClassVar[str] = PRINT_JOB_RECEIPT_AGGREGATE
    audience: ClassVar[frozenset[str]] = STAFF_AUDIENCE

    number: int
    """The print job's number (Druck 17)."""
    parts: int

    def public_payload(self) -> JsonObject:
        return {"job_id": str(self.aggregate_id), "number": self.number, "parts": self.parts}
