"""Who reads the newsletter: ask in the account, confirm by link, leave by link or account."""

from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

import structlog

from modellbahn.modules.newsletter.application.ports import UnitOfWorkFactory
from modellbahn.modules.newsletter.domain.errors import NewsletterTokenInvalidError
from modellbahn.modules.newsletter.domain.model import PENDING_RETENTION, Subscription
from modellbahn.platform.clock import Clock
from modellbahn.platform.security import generate_token, hash_token
from modellbahn.platform.uow import UniqueViolationError

_logger = structlog.get_logger(__name__)


class ReaderStatus(StrEnum):
    """What the account page shows."""

    NONE = "none"
    PENDING = "pending"
    CONFIRMED = "confirmed"


@dataclass(frozen=True, slots=True)
class Counts:
    confirmed: int
    pending: int


class SubscriptionService:
    def __init__(self, *, uow_factory: UnitOfWorkFactory, clock: Clock) -> None:
        self._uow = uow_factory
        self._clock = clock

    async def status(self, account_id: UUID) -> ReaderStatus:
        async with self._uow() as uow:
            subscription = await uow.subscriptions.by_account(account_id)
        if subscription is None:
            return ReaderStatus.NONE
        return ReaderStatus.CONFIRMED if subscription.is_confirmed else ReaderStatus.PENDING

    async def subscribe(self, account_id: UUID) -> ReaderStatus:
        """Ask for the newsletter: the confirmation mail follows (once the address is
        verified). Asking again resends the link, at most every ten minutes."""
        now = self._clock.now()
        async with self._uow() as uow:
            existing = await uow.subscriptions.by_account(account_id, for_update=True)
            if existing is None:
                subscription, event = Subscription.request(
                    account_id=account_id, unsubscribe_token=generate_token(), now=now
                )
                uow.subscriptions.add(subscription)
                uow.publish(event)
            else:
                if existing.is_confirmed:
                    return ReaderStatus.CONFIRMED
                again = existing.request_again(now)
                if again is not None:
                    uow.publish(again)
            try:
                await uow.commit()
            except UniqueViolationError:
                _logger.info("newsletter.subscription.concurrent_request")
        return ReaderStatus.PENDING

    async def unsubscribe_account(self, account_id: UUID) -> None:
        async with self._uow() as uow:
            subscription = await uow.subscriptions.by_account(account_id, for_update=True)
            if subscription is None:
                return
            await uow.subscriptions.delete(subscription)
            await uow.commit()
        _logger.info("newsletter.unsubscribed", via="account")

    async def confirm(self, token: str) -> None:
        async with self._uow() as uow:
            subscription = await uow.subscriptions.by_confirm_token(hash_token(token))
            if subscription is None:
                raise NewsletterTokenInvalidError
            subscription.confirm(self._clock.now())
            await uow.commit()

    async def unsubscribe(self, token: str) -> None:
        """Leave with the link from an issue. An unknown link counts as done."""
        async with self._uow() as uow:
            subscription = await uow.subscriptions.by_unsubscribe_token(token)
            if subscription is None:
                return
            await uow.subscriptions.delete(subscription)
            await uow.commit()
        _logger.info("newsletter.unsubscribed", via="link")

    async def counts(self) -> Counts:
        async with self._uow() as uow:
            counted = await uow.subscriptions.counts()
        return Counts(confirmed=counted["confirmed"], pending=counted["pending"])

    async def purge_pending(self) -> int:
        """Forget requests nobody confirmed within two weeks (no consent, no data)."""
        cutoff = self._clock.now() - PENDING_RETENTION
        async with self._uow() as uow:
            removed = await uow.subscriptions.delete_pending_before(cutoff)
            await uow.commit()
        if removed:
            _logger.info("newsletter.subscriptions.purged", removed=removed)
        return removed
