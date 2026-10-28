"""Domain events of the site module."""

from dataclasses import dataclass
from typing import ClassVar, Final

from modellbahn.platform.events import DomainEvent, JsonObject, domain_event

FAIR_AGGREGATE: Final = "site.fair"
SUBSCRIPTION_AGGREGATE: Final = "site.subscription"


@domain_event
@dataclass(frozen=True, kw_only=True)
class FairAnnounced(DomainEvent):
    """Staff sent the fair news: every confirmed subscriber gets a mail about this fair."""

    event_type: ClassVar[str] = "site.fair.announced"
    aggregate_type: ClassVar[str] = FAIR_AGGREGATE
    audience: ClassVar[frozenset[str]] = frozenset({"staff"})

    name: str

    def public_payload(self) -> JsonObject:
        return {"fair_id": str(self.aggregate_id), "name": self.name}


@domain_event
@dataclass(frozen=True, kw_only=True)
class SubscriptionRequested(DomainEvent):
    """Someone asked for the fair news; the worker mails them the link to confirm.

    The payload carries nothing personal: the handler loads the address itself.
    """

    event_type: ClassVar[str] = "site.subscription.requested"
    aggregate_type: ClassVar[str] = SUBSCRIPTION_AGGREGATE
