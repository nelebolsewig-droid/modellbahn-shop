"""Outbox event handlers of the site module; the worker runs them.

* A sign-up gets the mail with the link to confirm it. The raw token exists only in
  this process and in the mail, never in the database, the logs or the outbox.
* An announced fair goes to every confirmed subscriber, one mail each. Every mail
  sent is recorded, so a retry after a failure continues where it stopped.
"""

import contextlib
from collections.abc import Sequence
from typing import Final

import structlog

from modellbahn.modules.site.application import mails
from modellbahn.modules.site.application.ports import UnitOfWorkFactory
from modellbahn.modules.site.domain.events import FairAnnounced, SubscriptionRequested
from modellbahn.modules.site.domain.model import Mailing
from modellbahn.platform.clock import Clock
from modellbahn.platform.mail import Mailer, compose
from modellbahn.platform.outbox import HandlerRegistry
from modellbahn.platform.security import generate_token, hash_token
from modellbahn.platform.uow import ForeignKeyViolationError, UniqueViolationError

_logger = structlog.get_logger(__name__)

ANNOUNCEMENT_BATCH: Final = 50


class SiteHandlers:
    def __init__(
        self,
        *,
        uow_factory: UnitOfWorkFactory,
        mailer: Mailer,
        clock: Clock,
        public_base_url: str,
        shop_name: str,
        sender: Sequence[str] = (),
    ) -> None:
        self._uow = uow_factory
        self._mailer = mailer
        self._clock = clock
        self._base_url = public_base_url
        self._shop_name = shop_name
        self._sender = tuple(sender)

    def register(self, registry: HandlerRegistry) -> None:
        """Subscribe the handlers to their events."""
        registry.register(SubscriptionRequested, self.send_confirmation)
        registry.register(FairAnnounced, self.send_announcement)

    async def send_confirmation(self, event: SubscriptionRequested) -> None:
        token = generate_token()
        async with self._uow() as uow:
            subscription = await uow.subscriptions.get(event.aggregate_id)
            if subscription is None or subscription.is_confirmed:
                return
            subscription.issue_confirmation(hash_token(token), self._clock.now())
            await uow.commit()
        content = mails.confirmation_mail(
            base_url=self._base_url, token=token, shop_name=self._shop_name
        )
        await self._mailer.send(
            compose(content, to=subscription.email, shop_name=self._shop_name, sender=self._sender)
        )
        _logger.info("site.confirmation.sent", subscription_id=str(subscription.id))

    async def send_announcement(self, event: FairAnnounced) -> None:
        async with self._uow() as uow:
            fair = await uow.fairs.get(event.aggregate_id)
        if fair is None or not fair.published:
            _logger.info("site.announcement.skipped", fair_id=str(event.aggregate_id))
            return
        sent = 0
        while True:
            async with self._uow() as uow:
                batch = await uow.subscriptions.unsent(fair.id, ANNOUNCEMENT_BATCH)
            if not batch:
                break
            for subscription in batch:
                content = mails.announcement_mail(
                    fair,
                    base_url=self._base_url,
                    unsubscribe_token=subscription.unsubscribe_token,
                    shop_name=self._shop_name,
                )
                await self._mailer.send(
                    compose(
                        content,
                        to=subscription.email,
                        shop_name=self._shop_name,
                        sender=self._sender,
                    )
                )
                async with self._uow() as uow:
                    uow.subscriptions.record(
                        Mailing(
                            fair_id=fair.id,
                            subscription_id=subscription.id,
                            sent_at=self._clock.now(),
                        )
                    )
                    # Unsubscribed meanwhile, or recorded by an earlier attempt.
                    with contextlib.suppress(ForeignKeyViolationError, UniqueViolationError):
                        await uow.commit()
                sent += 1
        _logger.info("site.announcement.sent", fair_id=str(fair.id), mails=sent)
