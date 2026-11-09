"""Domain events of the AI module: the Stellwerk hears when a draft is ready or failed."""

from dataclasses import dataclass
from typing import ClassVar, Final
from uuid import UUID

from modellbahn.platform.events import DomainEvent, JsonObject, domain_event

RUN_AGGREGATE: Final = "ai.run"


@domain_event
@dataclass(frozen=True, kw_only=True)
class CopyDrafted(DomainEvent):
    """The model wrote a draft for the product; it waits for a person to take it over."""

    event_type: ClassVar[str] = "ai.copy.drafted"
    aggregate_type: ClassVar[str] = RUN_AGGREGATE
    audience: ClassVar[frozenset[str]] = frozenset({"staff"})

    product_id: UUID | None
    name: str

    def public_payload(self) -> JsonObject:
        return {
            "run_id": str(self.aggregate_id),
            "product_id": str(self.product_id) if self.product_id else None,
            "name": self.name,
        }


@domain_event
@dataclass(frozen=True, kw_only=True)
class CopyFailed(DomainEvent):
    """No draft came back: no budget left, the model declined, or the provider failed."""

    event_type: ClassVar[str] = "ai.copy.failed"
    aggregate_type: ClassVar[str] = RUN_AGGREGATE
    audience: ClassVar[frozenset[str]] = frozenset({"staff"})

    product_id: UUID | None
    name: str
    reason: str

    def public_payload(self) -> JsonObject:
        return {
            "run_id": str(self.aggregate_id),
            "product_id": str(self.product_id) if self.product_id else None,
            "name": self.name,
            "reason": self.reason,
        }
