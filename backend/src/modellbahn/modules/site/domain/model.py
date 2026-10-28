"""The site's model: the fairs the workshop exhibits at, and who wants to hear about them.

A **fair** is a date range at a venue, with the booth and opening hours. Only published
fairs appear in the shop; announcing one mails it once to every confirmed subscriber.

A **subscription** to the fair news follows double opt-in: asking for it stores the
address as *pending* and mails a link; only following that link confirms it. Pending
sign-ups that nobody confirms are deleted after a week, and unsubscribing deletes the
subscription at once, so the shop keeps no addresses it has no consent for.
"""

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from enum import StrEnum
from typing import Final
from uuid import UUID

from modellbahn.modules.site.domain.errors import (
    FairNotAnnounceableError,
    InvalidFieldError,
    SubscriptionTokenInvalidError,
)
from modellbahn.modules.site.domain.events import FairAnnounced, SubscriptionRequested
from modellbahn.platform.ids import new_id

FAIR_NAME_MAX_LENGTH: Final = 120
VENUE_MAX_LENGTH: Final = 120
STREET_MAX_LENGTH: Final = 120
POSTAL_CODE_MAX_LENGTH: Final = 10
CITY_MAX_LENGTH: Final = 80
BOOTH_MAX_LENGTH: Final = 60
HOURS_MAX_LENGTH: Final = 200
NOTE_MAX_LENGTH: Final = 500
URL_MAX_LENGTH: Final = 300
FAIR_DAYS_MAX: Final = 14

EMAIL_MAX_LENGTH: Final = 254
CONFIRMATION_LIFETIME: Final = timedelta(days=7)
# Asking again within this interval sends no second mail (no mail bombing via the form).
CONFIRMATION_RESEND_INTERVAL: Final = timedelta(minutes=10)
PENDING_RETENTION: Final = timedelta(days=7)
# The wording of the consent on the form, so a confirmation can be traced to it.
CONSENT_VERSION: Final = "messe-post-2026-10"

_URL: Final = re.compile(r"^https?://[^\s/$.?#][^\s]*$", re.IGNORECASE)
_EMAIL: Final = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _text(value: str, field: str, max_length: int, *, required: bool = False) -> str:
    cleaned = " ".join(value.split())
    if required and not cleaned:
        raise InvalidFieldError(field, "required", "must not be empty")
    if len(cleaned) > max_length:
        raise InvalidFieldError(field, "too_long", f"at most {max_length} characters")
    return cleaned


def _multiline(value: str, field: str, max_length: int) -> str:
    # Opening hours and notes may keep their line breaks, nothing else.
    lines = [" ".join(line.split()) for line in value.strip().splitlines()]
    cleaned = "\n".join(line for line in lines if line)
    if len(cleaned) > max_length:
        raise InvalidFieldError(field, "too_long", f"at most {max_length} characters")
    return cleaned


@dataclass(frozen=True, slots=True)
class FairDetails:
    """What staff fill in for a fair, checked and normalised by :meth:`checked`."""

    name: str
    venue: str
    street: str
    postal_code: str
    city: str
    booth: str
    hours: str
    website_url: str
    note: str
    starts_on: date
    ends_on: date

    def checked(self) -> "FairDetails":
        if self.ends_on < self.starts_on:
            raise InvalidFieldError("ends_on", "before_start", "the fair ends before it starts")
        if (self.ends_on - self.starts_on).days >= FAIR_DAYS_MAX:
            raise InvalidFieldError("ends_on", "too_long", f"at most {FAIR_DAYS_MAX} days")
        url = self.website_url.strip()
        if url and (len(url) > URL_MAX_LENGTH or not _URL.match(url)):
            raise InvalidFieldError("website_url", "invalid", "an http(s) address")
        return FairDetails(
            name=_text(self.name, "name", FAIR_NAME_MAX_LENGTH, required=True),
            venue=_text(self.venue, "venue", VENUE_MAX_LENGTH),
            street=_text(self.street, "street", STREET_MAX_LENGTH),
            postal_code=_text(self.postal_code, "postal_code", POSTAL_CODE_MAX_LENGTH),
            city=_text(self.city, "city", CITY_MAX_LENGTH, required=True),
            booth=_text(self.booth, "booth", BOOTH_MAX_LENGTH),
            hours=_multiline(self.hours, "hours", HOURS_MAX_LENGTH),
            website_url=url,
            note=_multiline(self.note, "note", NOTE_MAX_LENGTH),
            starts_on=self.starts_on,
            ends_on=self.ends_on,
        )


@dataclass(eq=False, kw_only=True)
class Fair:
    """A fair the workshop exhibits at."""

    id: UUID
    name: str
    venue: str
    street: str
    postal_code: str
    city: str
    booth: str
    hours: str
    website_url: str
    note: str
    starts_on: date
    ends_on: date
    published: bool
    announced_at: datetime | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def create(cls, details: FairDetails, *, published: bool, now: datetime) -> "Fair":
        fair = cls(
            id=new_id(),
            name="",
            venue="",
            street="",
            postal_code="",
            city="",
            booth="",
            hours="",
            website_url="",
            note="",
            starts_on=details.starts_on,
            ends_on=details.ends_on,
            published=published,
            announced_at=None,
            created_at=now,
            updated_at=now,
        )
        fair.change(details, published=published, now=now)
        return fair

    def change(self, details: FairDetails, *, published: bool, now: datetime) -> None:
        checked = details.checked()
        self.name = checked.name
        self.venue = checked.venue
        self.street = checked.street
        self.postal_code = checked.postal_code
        self.city = checked.city
        self.booth = checked.booth
        self.hours = checked.hours
        self.website_url = checked.website_url
        self.note = checked.note
        self.starts_on = checked.starts_on
        self.ends_on = checked.ends_on
        self.published = published
        self.updated_at = now

    def is_over(self, today: date) -> bool:
        return self.ends_on < today

    def announce(self, *, today: date, now: datetime) -> FairAnnounced:
        """Send the fair news about this fair, once, while it is still to come."""
        if not self.published:
            raise FairNotAnnounceableError("not_published")
        if self.is_over(today):
            raise FairNotAnnounceableError("past")
        if self.announced_at is not None:
            raise FairNotAnnounceableError("already_announced")
        self.announced_at = now
        self.updated_at = now
        return FairAnnounced(aggregate_id=self.id, occurred_at=now, name=self.name)

    def place(self) -> str:
        """``JohannStadthalle, Holbeinstraße 68, 01307 Dresden``."""
        town = " ".join(part for part in (self.postal_code, self.city) if part)
        return ", ".join(part for part in (self.venue, self.street, town) if part)


def normalize_email(value: str) -> str:
    """Trimmed and checked; the domain part in lower case (the local part is the sender's)."""
    cleaned = value.strip()
    if len(cleaned) > EMAIL_MAX_LENGTH or not _EMAIL.match(cleaned):
        raise InvalidFieldError("email", "invalid", "not an e-mail address")
    local, _, domain = cleaned.rpartition("@")
    return f"{local}@{domain.lower()}"


class SubscriptionStatus(StrEnum):
    PENDING = "pending"
    CONFIRMED = "confirmed"


@dataclass(eq=False, kw_only=True)
class Subscription:
    """One address that asked for the fair news; ``confirmed`` once the link was followed.

    The unsubscribe token is stored as it is, unlike the confirmation token: every
    mail carries it, and all it can do is end the subscription.
    """

    id: UUID
    email: str
    status: SubscriptionStatus
    consent: str
    unsubscribe_token: str
    confirm_token_hash: str | None
    confirm_expires_at: datetime | None
    confirm_requested_at: datetime
    confirmed_at: datetime | None
    created_at: datetime

    @classmethod
    def request(
        cls, *, email: str, unsubscribe_token: str, now: datetime
    ) -> tuple["Subscription", SubscriptionRequested]:
        subscription = cls(
            id=new_id(),
            email=normalize_email(email),
            status=SubscriptionStatus.PENDING,
            consent=CONSENT_VERSION,
            unsubscribe_token=unsubscribe_token,
            confirm_token_hash=None,
            confirm_expires_at=None,
            confirm_requested_at=now,
            confirmed_at=None,
            created_at=now,
        )
        return subscription, SubscriptionRequested(aggregate_id=subscription.id, occurred_at=now)

    @property
    def is_confirmed(self) -> bool:
        return self.status is SubscriptionStatus.CONFIRMED

    def request_again(self, now: datetime) -> SubscriptionRequested | None:
        """Someone asked once more: a new link, unless confirmed or asked a moment ago."""
        if self.is_confirmed or now - self.confirm_requested_at < CONFIRMATION_RESEND_INTERVAL:
            return None
        self.confirm_requested_at = now
        self.consent = CONSENT_VERSION
        return SubscriptionRequested(aggregate_id=self.id, occurred_at=now)

    def issue_confirmation(self, token_hash: str, now: datetime) -> None:
        """The link in the mail about to go out; an earlier link stops working."""
        self.confirm_token_hash = token_hash
        self.confirm_expires_at = now + CONFIRMATION_LIFETIME

    def confirm(self, now: datetime) -> None:
        if self.confirm_expires_at is None or now >= self.confirm_expires_at:
            raise SubscriptionTokenInvalidError
        self.status = SubscriptionStatus.CONFIRMED
        self.confirmed_at = now
        self.confirm_token_hash = None
        self.confirm_expires_at = None


@dataclass(eq=False, kw_only=True)
class Mailing:
    """The announcement of ``fair_id`` went to ``subscription_id``: never send it twice."""

    fair_id: UUID
    subscription_id: UUID
    sent_at: datetime
