"""Domain events of the identity module.

Payloads never carry secrets or e-mail addresses: handlers load what they need
from the account. Events addressed to the ``staff`` audience show up live in the
admin area; their public payload is limited to the account id and display name.
"""

from dataclasses import dataclass
from typing import ClassVar, Final

from modellbahn.platform.events import DomainEvent, JsonObject, domain_event

ACCOUNT_AGGREGATE: Final = "identity.account"
STAFF_AUDIENCE: Final = frozenset({"staff"})


@domain_event
@dataclass(frozen=True, kw_only=True)
class CustomerRegistered(DomainEvent):
    """A new customer account was created; it still needs its e-mail address verified."""

    event_type: ClassVar[str] = "identity.customer.registered"
    aggregate_type: ClassVar[str] = ACCOUNT_AGGREGATE
    audience: ClassVar[frozenset[str]] = STAFF_AUDIENCE

    display_name: str

    def public_payload(self) -> JsonObject:
        return {"account_id": str(self.aggregate_id), "display_name": self.display_name}


@domain_event
@dataclass(frozen=True, kw_only=True)
class RegistrationAttemptedForExistingAccount(DomainEvent):
    """Someone tried to register with the address of an existing customer account."""

    event_type: ClassVar[str] = "identity.customer.registration_attempted_existing"
    aggregate_type: ClassVar[str] = ACCOUNT_AGGREGATE


@domain_event
@dataclass(frozen=True, kw_only=True)
class VerificationMailRequested(DomainEvent):
    """An unverified customer asked for a new verification e-mail."""

    event_type: ClassVar[str] = "identity.customer.verification_requested"
    aggregate_type: ClassVar[str] = ACCOUNT_AGGREGATE


@domain_event
@dataclass(frozen=True, kw_only=True)
class EmailVerified(DomainEvent):
    """A customer proved control of the e-mail address (needed to adopt guest orders)."""

    event_type: ClassVar[str] = "identity.account.email_verified"
    aggregate_type: ClassVar[str] = ACCOUNT_AGGREGATE
    audience: ClassVar[frozenset[str]] = STAFF_AUDIENCE

    display_name: str

    def public_payload(self) -> JsonObject:
        return {"account_id": str(self.aggregate_id), "display_name": self.display_name}


@domain_event
@dataclass(frozen=True, kw_only=True)
class PasswordResetRequested(DomainEvent):
    """A customer asked for a link to set a new password."""

    event_type: ClassVar[str] = "identity.account.password_reset_requested"
    aggregate_type: ClassVar[str] = ACCOUNT_AGGREGATE


@domain_event
@dataclass(frozen=True, kw_only=True)
class PasswordChanged(DomainEvent):
    """The password of an account was changed or reset."""

    event_type: ClassVar[str] = "identity.account.password_changed"
    aggregate_type: ClassVar[str] = ACCOUNT_AGGREGATE


@domain_event
@dataclass(frozen=True, kw_only=True)
class AccountDeleted(DomainEvent):
    """An account was anonymised; other modules remove their personal data about it."""

    event_type: ClassVar[str] = "identity.account.deleted"
    aggregate_type: ClassVar[str] = ACCOUNT_AGGREGATE
