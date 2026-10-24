"""Domain events of the catalogue module.

Publishing and archiving show up live in the admin area; the public payload is the
product id and name. ``updated`` marks changes to a product in the shop, for caches
that must be refreshed.
"""

from dataclasses import dataclass
from typing import ClassVar, Final

from modellbahn.platform.events import DomainEvent, JsonObject, domain_event

PRODUCT_AGGREGATE: Final = "catalog.product"
STAFF_AUDIENCE: Final = frozenset({"staff"})


@domain_event
@dataclass(frozen=True, kw_only=True)
class ProductPublished(DomainEvent):
    """The product is in the shop."""

    event_type: ClassVar[str] = "catalog.product.published"
    aggregate_type: ClassVar[str] = PRODUCT_AGGREGATE
    audience: ClassVar[frozenset[str]] = STAFF_AUDIENCE

    name: str
    slug: str

    def public_payload(self) -> JsonObject:
        return {"product_id": str(self.aggregate_id), "name": self.name}


@domain_event
@dataclass(frozen=True, kw_only=True)
class ProductArchived(DomainEvent):
    """The product left the shop; orders and stock keep referring to it."""

    event_type: ClassVar[str] = "catalog.product.archived"
    aggregate_type: ClassVar[str] = PRODUCT_AGGREGATE
    audience: ClassVar[frozenset[str]] = STAFF_AUDIENCE

    name: str
    slug: str

    def public_payload(self) -> JsonObject:
        return {"product_id": str(self.aggregate_id), "name": self.name}


@domain_event
@dataclass(frozen=True, kw_only=True)
class ProductUpdated(DomainEvent):
    """A product in the shop changed (text, prices, gauges, gallery)."""

    event_type: ClassVar[str] = "catalog.product.updated"
    aggregate_type: ClassVar[str] = PRODUCT_AGGREGATE

    slug: str
