"""The fair news by e-mail, with double opt-in: ask, confirm by link, leave by link."""

from datetime import datetime

import structlog

from modellbahn.modules.site.application.ports import UnitOfWorkFactory
from modellbahn.modules.site.domain.errors import SubscriptionTokenInvalidError
from modellbahn.modules.site.domain.model import (
    PENDING_RETENTION,
    Subscription,
    normalize_email,
)
from modellbahn.platform.clock import Clock
from modellbahn.platform.security import generate_token, hash_token
from modellbahn.platform.uow import UniqueViolationError

_logger = structlog.get_logger(__name__)


class SubscriptionService:
    def __init__(self, *, uow_factory: UnitOfWorkFactory, clock: Clock) -> None:
        self._uow = uow_factory
        self._clock = clock

    async def subscribe(self, email: str) -> None:
        """Ask for the fair news. The answer is the same whether or not the address is
        known, so the form tells nobody who is subscribed."""
        address = normalize_email(email)
        now = self._clock.now()
        async with self._uow() as uow:
            existing = await uow.subscriptions.by_email(address, for_update=True)
            if existing is None:
                subscription, event = Subscription.request(
                    email=address, unsubscribe_token=generate_token(), now=now
                )
                uow.subscriptions.add(subscription)
                uow.publish(event)
            else:
                again = existing.request_again(now)
                if again is None:
                    return
                uow.publish(again)
            try:
                await uow.commit()
            except UniqueViolationError:
                # The same address asked twice at the same moment; the first one wins.
                _logger.info("site.subscription.concurrent_request")

    async def confirm(self, token: str) -> None:
        async with self._uow() as uow:
            subscription = await uow.subscriptions.by_confirm_token(hash_token(token))
            if subscription is None:
                raise SubscriptionTokenInvalidError
            subscription.confirm(self._clock.now())
            await uow.commit()

    async def unsubscribe(self, token: str) -> None:
        """Leave the fair news. An unknown link counts as done: perhaps it was used before."""
        async with self._uow() as uow:
            subscription = await uow.subscriptions.by_unsubscribe_token(token)
            if subscription is None:
                return
            await uow.subscriptions.delete(subscription)
            await uow.commit()

    async def counts(self) -> dict[str, int]:
        async with self._uow() as uow:
            return await uow.subscriptions.counts()

    async def purge_pending(self) -> int:
        """Forget sign-ups nobody confirmed within a week (no consent, no data)."""
        cutoff: datetime = self._clock.now() - PENDING_RETENTION
        async with self._uow() as uow:
            removed = await uow.subscriptions.delete_pending_before(cutoff)
            await uow.commit()
        if removed:
            _logger.info("site.subscriptions.purged", removed=removed)
        return removed
