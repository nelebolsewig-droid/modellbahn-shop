"""Domain events of the newsletter module. Payloads carry nothing personal."""

from dataclasses import dataclass
from typing import ClassVar, Final

from modellbahn.platform.events import DomainEvent, JsonObject, domain_event

SUBSCRIPTION_AGGREGATE: Final = "newsletter.subscription"
ISSUE_AGGREGATE: Final = "newsletter.issue"


@domain_event
@dataclass(frozen=True, kw_only=True)
class NewsletterRequested(DomainEvent):
    """A customer asked for the newsletter; the worker mails the link to confirm it
    (once the account's address is verified)."""

    event_type: ClassVar[str] = "newsletter.subscription.requested"
    aggregate_type: ClassVar[str] = SUBSCRIPTION_AGGREGATE


@domain_event
@dataclass(frozen=True, kw_only=True)
class IssueReleased(DomainEvent):
    """An issue is due: the worker mails it to every confirmed reader, once each."""

    event_type: ClassVar[str] = "newsletter.issue.released"
    aggregate_type: ClassVar[str] = ISSUE_AGGREGATE
    audience: ClassVar[frozenset[str]] = frozenset({"staff"})

    number: int
    new_models: int

    def public_payload(self) -> JsonObject:
        return {"issue_id": str(self.aggregate_id), "number": self.number}
