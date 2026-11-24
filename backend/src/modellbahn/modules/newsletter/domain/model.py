"""The newsletter's model: who reads it, which issues went out, and what suits whom.

A **subscription** belongs to a customer account and follows double opt-in: asking for
it (at registration or in the account) stores it as *pending*; the mail with the link
goes out once the account's address is verified, and only following the link confirms
it. Unconfirmed requests are deleted after two weeks; unsubscribing deletes it at once.
The address is never copied: every issue goes to the account's current address.

An **issue** goes out on fixed days of the month (the 1st and the 15th by default), but
only if new models came into the shop since the issue before. Each mail sent is noted as
a **delivery**, so a retry continues where it stopped and nobody gets an issue twice.
"""

from collections.abc import Collection, Iterable, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from enum import StrEnum
from typing import Final
from uuid import UUID

from modellbahn.modules.newsletter.domain.errors import NewsletterTokenInvalidError
from modellbahn.modules.newsletter.domain.events import IssueReleased, NewsletterRequested
from modellbahn.platform.ids import new_id

CONFIRMATION_LIFETIME: Final = timedelta(days=7)
CONFIRMATION_RESEND_INTERVAL: Final = timedelta(minutes=10)
PENDING_RETENTION: Final = timedelta(days=14)
# The wording of the consent in the shop, so a confirmation can be traced to it.
CONSENT_VERSION: Final = "newsletter-2026-11"
# The first issue looks back this far for new models.
FIRST_ISSUE_LOOKBACK: Final = timedelta(days=30)
NEW_MODELS_MAX: Final = 6
SUGGESTIONS_MAX: Final = 3


class SubscriptionStatus(StrEnum):
    PENDING = "pending"
    CONFIRMED = "confirmed"


@dataclass(eq=False, kw_only=True)
class Subscription:
    """The newsletter of one customer account; ``confirmed`` once the link was followed.

    The unsubscribe token is stored as it is: every issue carries it, and all it can do
    is end the subscription.
    """

    id: UUID
    account_id: UUID
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
        cls, *, account_id: UUID, unsubscribe_token: str, now: datetime
    ) -> tuple["Subscription", NewsletterRequested]:
        subscription = cls(
            id=new_id(),
            account_id=account_id,
            status=SubscriptionStatus.PENDING,
            consent=CONSENT_VERSION,
            unsubscribe_token=unsubscribe_token,
            confirm_token_hash=None,
            confirm_expires_at=None,
            confirm_requested_at=now,
            confirmed_at=None,
            created_at=now,
        )
        return subscription, NewsletterRequested(aggregate_id=subscription.id, occurred_at=now)

    @property
    def is_confirmed(self) -> bool:
        return self.status is SubscriptionStatus.CONFIRMED

    def request_again(self, now: datetime) -> NewsletterRequested | None:
        """Asked once more: a new link, unless confirmed or asked a moment ago."""
        if self.is_confirmed or now - self.confirm_requested_at < CONFIRMATION_RESEND_INTERVAL:
            return None
        self.confirm_requested_at = now
        self.consent = CONSENT_VERSION
        return NewsletterRequested(aggregate_id=self.id, occurred_at=now)

    @property
    def awaits_link(self) -> bool:
        """Was it asked for after the last link went out (or did none go out yet)?
        The request and the verification of the address both send the link; whichever
        comes second finds it sent."""
        if self.is_confirmed:
            return False
        if self.confirm_expires_at is None:
            return True
        return self.confirm_expires_at - CONFIRMATION_LIFETIME < self.confirm_requested_at

    def issue_confirmation(self, token_hash: str, now: datetime) -> None:
        """The link in the mail about to go out; an earlier link stops working."""
        self.confirm_token_hash = token_hash
        self.confirm_expires_at = now + CONFIRMATION_LIFETIME

    def confirm(self, now: datetime) -> None:
        if self.confirm_expires_at is None or now >= self.confirm_expires_at:
            raise NewsletterTokenInvalidError
        self.status = SubscriptionStatus.CONFIRMED
        self.confirmed_at = now
        self.confirm_token_hash = None
        self.confirm_expires_at = None


@dataclass(eq=False, kw_only=True)
class Issue:
    """One newsletter: the models new since ``new_since`` and a suggestion per reader."""

    id: UUID
    number: int
    issue_date: date
    new_since: datetime
    new_product_ids: list[UUID]
    created_at: datetime

    @classmethod
    def release(
        cls,
        *,
        number: int,
        issue_date: date,
        new_since: datetime,
        new_product_ids: Sequence[UUID],
        now: datetime,
    ) -> tuple["Issue", IssueReleased]:
        issue = cls(
            id=new_id(),
            number=number,
            issue_date=issue_date,
            new_since=new_since,
            new_product_ids=list(new_product_ids),
            created_at=now,
        )
        event = IssueReleased(
            aggregate_id=issue.id,
            occurred_at=now,
            number=number,
            new_models=len(new_product_ids),
        )
        return issue, event


@dataclass(eq=False, kw_only=True)
class Delivery:
    """Issue ``issue_id`` went to ``subscription_id``: never send it twice."""

    issue_id: UUID
    subscription_id: UUID
    sent_at: datetime


def is_issue_day(day: date, issue_days: Collection[int]) -> bool:
    """Is ``day`` one of the days of the month an issue goes out? A day beyond the end
    of a month (the 31st) falls on the month's last day."""
    last = _last_day_of_month(day)
    return any(min(wanted, last.day) == day.day for wanted in issue_days)


def _last_day_of_month(day: date) -> date:
    following = day.replace(day=28) + timedelta(days=4)
    return following - timedelta(days=following.day)


def next_issue_day(after: date, issue_days: Collection[int]) -> date | None:
    """The next issue day from ``after`` on (inclusive); None if no days are set."""
    if not issue_days:
        return None
    day = after
    for _ in range(62):
        if is_issue_day(day, issue_days):
            return day
        day += timedelta(days=1)
    return None


@dataclass(frozen=True, slots=True)
class Model:
    """A model in the shop, as far as choosing for a reader goes."""

    product_id: UUID
    slug: str
    published_at: datetime | None
    category_ids: tuple[UUID, ...]
    """Its category and the parents, the most specific first."""
    scale_codes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Bought:
    """A model a reader bought, in the scale they bought it in."""

    slug: str
    scale_code: str


def new_models(models: Iterable[Model], since: datetime) -> list[Model]:
    """Models that came into the shop after ``since`` (the last issue), the newest first."""
    fresh = [m for m in models if m.published_at is not None and m.published_at > since]
    fresh.sort(key=lambda m: m.published_at or since, reverse=True)
    return fresh


def suggest(
    models: Sequence[Model],
    bought: Collection[Bought],
    *,
    shown: Collection[UUID],
    limit: int = SUGGESTIONS_MAX,
) -> list[Model]:
    """What suits a reader: models in a scale they collect and close to what they bought.

    Never something they own already, nor what the issue ``shown`` among the new models.
    A model scores for sharing a category with something they bought (the more specific,
    the more); a model in none of their scales does not count. Nobody who bought nothing
    gets suggestions: the new models speak for themselves.
    """
    if not bought:
        return []
    owned = {b.slug for b in bought}
    scales = {b.scale_code for b in bought}
    by_slug = {m.slug: m for m in models}
    weights: dict[UUID, int] = {}
    for b in bought:
        model = by_slug.get(b.slug)
        if model is None:
            continue
        for depth, category_id in enumerate(model.category_ids):
            # The model's own category counts most, its parents less and less.
            weights[category_id] = max(weights.get(category_id, 0), 3 - min(depth, 2))
    scored: list[tuple[int, int, Model]] = []
    for position, model in enumerate(models):
        if (
            model.slug in owned
            or model.product_id in shown
            or not scales.intersection(model.scale_codes)
        ):
            continue
        score = sum(weights.get(c, 0) for c in model.category_ids[:1]) * 2 + max(
            (weights.get(c, 0) for c in model.category_ids), default=0
        )
        if score > 0:
            scored.append((score, position, model))
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [model for _, _, model in scored[:limit]]
