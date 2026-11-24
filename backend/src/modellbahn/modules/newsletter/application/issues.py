"""The issues: released by the worker on the issue days, written for each reader.

The worker asks every hour whether an issue is due (:meth:`IssueService.release_if_due`):
on an issue day, during the day, if no issue went out that day and new models came into
the shop since the last one. The release is an outbox event; the handler then mails it.
"""

from collections.abc import Collection, Sequence
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Final
from uuid import UUID
from zoneinfo import ZoneInfo

import structlog

from modellbahn.modules.catalog.contracts.showcase import ShowcaseProduct
from modellbahn.modules.media.contracts.images import ImageView
from modellbahn.modules.newsletter.application import mails
from modellbahn.modules.newsletter.application.ports import UnitOfWorkFactory
from modellbahn.modules.newsletter.domain.model import (
    FIRST_ISSUE_LOOKBACK,
    NEW_MODELS_MAX,
    Bought,
    Issue,
    Model,
    is_issue_day,
    new_models,
    next_issue_day,
    suggest,
)
from modellbahn.modules.sales.contracts.purchases import Purchase
from modellbahn.platform.clock import Clock
from modellbahn.platform.mail import MailCard, MailContent, OutgoingMail, compose
from modellbahn.platform.money import format_euro
from modellbahn.platform.uow import UniqueViolationError

_logger = structlog.get_logger(__name__)

SHOP_TIME_ZONE: Final = ZoneInfo("Europe/Berlin")
# Issues go out in the morning, when mails are read; a worker down then catches up later.
SEND_FROM: Final = time(9, 0)
SEND_UNTIL: Final = time(20, 0)
RECENT_ISSUES: Final = 12
_CARD_RENDITION: Final = "thumb"
# The preview's unsubscribe link leads nowhere.
SAMPLE_TOKEN: Final = "beispiel"  # noqa: S105


@dataclass(frozen=True, slots=True)
class Edition:
    """What an issue shows, read once and written for each reader."""

    models: list[Model]
    products: dict[UUID, ShowcaseProduct]
    new_ids: list[UUID]
    images: dict[UUID, ImageView]


@dataclass(frozen=True, slots=True)
class PastIssue:
    number: int
    issue_date: date
    new_models: int
    sent: int


@dataclass(frozen=True, slots=True)
class Overview:
    """The newsletter in the Stellwerk."""

    issue_days: tuple[int, ...]
    next_issue: date | None
    waiting: list[str]
    """Names of the models new since the last issue: they go into the next one."""
    recent: list[PastIssue]


def to_model(product: ShowcaseProduct) -> Model:
    return Model(
        product_id=product.product_id,
        slug=product.slug,
        published_at=product.published_at,
        category_ids=product.category_ids,
        scale_codes=product.scale_codes,
    )


def bought_of(purchases: Collection[Purchase]) -> list[Bought]:
    return [Bought(slug=p.product_slug, scale_code=p.scale_code) for p in purchases]


class IssueWriter:
    """Writes the mail of an issue for one reader."""

    def __init__(self, *, public_base_url: str, shop_name: str, sender: Sequence[str]) -> None:
        self._base_url = public_base_url
        self._shop_name = shop_name
        self._sender = tuple(sender)

    def content(
        self,
        edition: Edition,
        *,
        number: int,
        display_name: str,
        bought: Collection[Bought],
        unsubscribe_token: str,
    ) -> MailContent:
        shown = edition.new_ids[:NEW_MODELS_MAX]
        suggestions = suggest(edition.models, bought, shown=set(shown))
        return mails.issue_mail(
            number=number,
            display_name=display_name,
            new_cards=[self._card(edition, product_id) for product_id in shown],
            suggestion_cards=[self._card(edition, m.product_id) for m in suggestions],
            base_url=self._base_url,
            unsubscribe_token=unsubscribe_token,
            shop_name=self._shop_name,
        )

    def mail(self, content: MailContent, *, to: str, unsubscribe_token: str) -> OutgoingMail:
        return compose(
            content,
            to=to,
            shop_name=self._shop_name,
            sender=self._sender,
            unsubscribe_url=mails.one_click_link(self._base_url, unsubscribe_token),
        )

    def _card(self, edition: Edition, product_id: UUID) -> MailCard:
        product = edition.products[product_id]
        price = (
            f"ab {format_euro(product.price_from_cents)}"
            if product.price_from_cents is not None
            else ""
        )
        return MailCard(
            title=product.name,
            url=f"{self._base_url}/produkte/{product.slug}",
            text=product.summary,
            price=price,
            image_url=_image_url(edition.images.get(product.image_asset_id))
            if product.image_asset_id
            else None,
        )


def _image_url(image: ImageView | None) -> str | None:
    if image is None or not image.is_ready:
        return None
    for rendition in image.renditions:
        if rendition.name == _CARD_RENDITION:
            return rendition.url
    return None


async def read_edition(uow_factory: UnitOfWorkFactory, new_ids: Sequence[UUID]) -> Edition:
    """The shop's models as they are now; models gone from the shop are left out."""
    async with uow_factory() as uow:
        showcase = await uow.shop.showcase()
        products = {p.product_id: p for p in showcase}
        shown = [product_id for product_id in new_ids if product_id in products]
        images = await uow.shop.images(
            [p.image_asset_id for p in showcase if p.image_asset_id is not None]
        )
    return Edition(
        models=[to_model(p) for p in showcase], products=products, new_ids=shown, images=images
    )


class IssueService:
    def __init__(
        self,
        *,
        uow_factory: UnitOfWorkFactory,
        clock: Clock,
        issue_days: Collection[int],
        writer: IssueWriter,
    ) -> None:
        self._uow = uow_factory
        self._clock = clock
        self._issue_days = tuple(sorted(set(issue_days)))
        self._writer = writer

    async def release_if_due(self) -> bool:
        """Release today's issue if it is due and there is something new; True if so."""
        now = self._clock.now()
        local = now.astimezone(SHOP_TIME_ZONE)
        if not self._is_due(local):
            return False
        async with self._uow() as uow:
            latest = await uow.issues.latest()
            if latest is not None and latest.issue_date >= local.date():
                return False
            since = latest.created_at if latest is not None else now - FIRST_ISSUE_LOOKBACK
            fresh = new_models([to_model(p) for p in await uow.shop.showcase()], since)
            if not fresh:
                _logger.info("newsletter.issue.nothing_new", day=local.date().isoformat())
                return False
            issue, event = Issue.release(
                number=(latest.number + 1) if latest is not None else 1,
                issue_date=local.date(),
                new_since=since,
                new_product_ids=[m.product_id for m in fresh],
                now=now,
            )
            uow.issues.add(issue)
            uow.publish(event)
            try:
                await uow.commit()
            except UniqueViolationError:
                # Another worker released it a moment ago.
                return False
        _logger.info("newsletter.issue.released", number=issue.number, new_models=len(fresh))
        return True

    def _is_due(self, local: datetime) -> bool:
        return (
            bool(self._issue_days)
            and is_issue_day(local.date(), self._issue_days)
            and SEND_FROM <= local.time() < SEND_UNTIL
        )

    async def overview(self) -> Overview:
        now = self._clock.now()
        today = now.astimezone(SHOP_TIME_ZONE).date()
        async with self._uow() as uow:
            latest = await uow.issues.latest()
            recent = await uow.issues.recent(RECENT_ISSUES)
            showcase = await uow.shop.showcase()
        since = latest.created_at if latest is not None else now - FIRST_ISSUE_LOOKBACK
        names = {p.product_id: p.name for p in showcase}
        waiting = [names[m.product_id] for m in new_models(map(to_model, showcase), since)]
        done_today = latest is not None and latest.issue_date >= today
        too_late = now.astimezone(SHOP_TIME_ZONE).time() >= SEND_UNTIL
        start = today + timedelta(days=1) if done_today or too_late else today
        return Overview(
            issue_days=self._issue_days,
            next_issue=next_issue_day(start, self._issue_days),
            waiting=waiting,
            recent=[
                PastIssue(
                    number=issue.number,
                    issue_date=issue.issue_date,
                    new_models=len(issue.new_product_ids),
                    sent=sent,
                )
                for issue, sent in recent
            ],
        )

    async def preview(self) -> tuple[OutgoingMail, str | None]:
        """The next issue as a sample reader would get it, with the model the sample
        reader is assumed to own (for the suggestions), if there is one."""
        now = self._clock.now()
        async with self._uow() as uow:
            latest = await uow.issues.latest()
            showcase = await uow.shop.showcase()
        since = latest.created_at if latest is not None else now - FIRST_ISSUE_LOOKBACK
        fresh = new_models(map(to_model, showcase), since)
        edition = await read_edition(self._uow, [m.product_id for m in fresh])
        fresh_ids = {m.product_id for m in fresh}
        older = [p for p in showcase if p.product_id not in fresh_ids]
        sample = older[-1] if older else None
        bought = [Bought(sample.slug, sample.scale_codes[0])] if sample is not None else []
        content = self._writer.content(
            edition,
            number=(latest.number + 1) if latest is not None else 1,
            display_name="Max Mustermann",
            bought=bought,
            unsubscribe_token=SAMPLE_TOKEN,
        )
        mail = self._writer.mail(content, to="beispiel@example.com", unsubscribe_token=SAMPLE_TOKEN)
        return mail, sample.name if sample is not None else None
