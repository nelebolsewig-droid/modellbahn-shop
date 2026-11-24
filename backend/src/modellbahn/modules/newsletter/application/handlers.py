"""Outbox event handlers of the newsletter; the worker runs them.

* A request gets the mail with the link to confirm it, but only to a verified address:
  if the account is not verified yet, the mail follows its verification.
* A customer who ticked the newsletter at registration gets such a request.
* A deleted account loses its subscription.
* A released issue goes to every confirmed reader, written for each of them. Every mail
  sent is recorded, so a retry continues where it stopped.
"""

import contextlib
from collections.abc import Sequence
from typing import Final
from uuid import UUID

import structlog

from modellbahn.modules.identity.contracts.events import (
    AccountDeleted,
    CustomerRegistered,
    EmailVerified,
)
from modellbahn.modules.newsletter.application import mails
from modellbahn.modules.newsletter.application.issues import (
    IssueWriter,
    bought_of,
    read_edition,
)
from modellbahn.modules.newsletter.application.ports import UnitOfWorkFactory
from modellbahn.modules.newsletter.application.subscriptions import SubscriptionService
from modellbahn.modules.newsletter.domain.events import IssueReleased, NewsletterRequested
from modellbahn.modules.newsletter.domain.model import Delivery
from modellbahn.platform.clock import Clock
from modellbahn.platform.mail import Mailer, compose
from modellbahn.platform.outbox import HandlerRegistry
from modellbahn.platform.security import generate_token, hash_token
from modellbahn.platform.uow import ForeignKeyViolationError, UniqueViolationError

_logger = structlog.get_logger(__name__)

ISSUE_BATCH: Final = 50


class NewsletterHandlers:
    def __init__(
        self,
        *,
        uow_factory: UnitOfWorkFactory,
        mailer: Mailer,
        clock: Clock,
        public_base_url: str,
        shop_name: str,
        sender: Sequence[str] = (),
        writer: IssueWriter,
    ) -> None:
        self._uow = uow_factory
        self._mailer = mailer
        self._clock = clock
        self._base_url = public_base_url
        self._shop_name = shop_name
        self._sender = tuple(sender)
        self._writer = writer
        self._subscriptions = SubscriptionService(uow_factory=uow_factory, clock=clock)

    def register(self, registry: HandlerRegistry) -> None:
        """Subscribe the handlers to their events."""
        registry.register(NewsletterRequested, self.send_confirmation)
        registry.register(CustomerRegistered, self.subscribe_new_customer, name="newsletter")
        registry.register(EmailVerified, self.confirm_after_verification, name="newsletter")
        registry.register(AccountDeleted, self.forget_account, name="newsletter")
        registry.register(IssueReleased, self.send_issue)

    async def subscribe_new_customer(self, event: CustomerRegistered) -> None:
        if event.newsletter:
            await self._subscriptions.subscribe(event.aggregate_id)

    async def confirm_after_verification(self, event: EmailVerified) -> None:
        async with self._uow() as uow:
            subscription = await uow.subscriptions.by_account(event.aggregate_id)
        if subscription is not None and subscription.awaits_link:
            await self._send_confirmation(subscription.id)

    async def forget_account(self, event: AccountDeleted) -> None:
        await self._subscriptions.unsubscribe_account(event.aggregate_id)

    async def send_confirmation(self, event: NewsletterRequested) -> None:
        await self._send_confirmation(event.aggregate_id)

    async def _send_confirmation(self, subscription_id: UUID) -> None:
        token = generate_token()
        async with self._uow() as uow:
            subscription = await uow.subscriptions.get(subscription_id)
            if subscription is None or not subscription.awaits_link:
                return
            account = await uow.shop.account(subscription.account_id)
            if account is None or not account.active:
                return
            if not account.email_verified:
                # The link follows the verification of the address (EmailVerified).
                _logger.info("newsletter.confirmation.awaits_verification")
                return
            subscription.issue_confirmation(hash_token(token), self._clock.now())
            await uow.commit()
        content = mails.confirmation_mail(
            base_url=self._base_url,
            token=token,
            shop_name=self._shop_name,
            display_name=account.display_name,
        )
        await self._mailer.send(
            compose(content, to=account.email, shop_name=self._shop_name, sender=self._sender)
        )
        _logger.info("newsletter.confirmation.sent", subscription_id=str(subscription.id))

    async def send_issue(self, event: IssueReleased) -> None:
        async with self._uow() as uow:
            issue = await uow.issues.get(event.aggregate_id)
        if issue is None:
            return
        edition = await read_edition(self._uow, issue.new_product_ids)
        sent = 0
        while True:
            async with self._uow() as uow:
                batch = await uow.subscriptions.unsent(issue.id, ISSUE_BATCH)
            if not batch:
                break
            for subscription in batch:
                async with self._uow() as uow:
                    account = await uow.shop.account(subscription.account_id)
                    purchases = await uow.shop.purchases(subscription.account_id)
                if account is not None and account.active and account.email_verified:
                    content = self._writer.content(
                        edition,
                        number=issue.number,
                        display_name=account.display_name,
                        bought=bought_of(purchases),
                        unsubscribe_token=subscription.unsubscribe_token,
                    )
                    await self._mailer.send(
                        self._writer.mail(
                            content,
                            to=account.email,
                            unsubscribe_token=subscription.unsubscribe_token,
                        )
                    )
                    sent += 1
                async with self._uow() as uow:
                    # Recorded also when skipped, so the loop moves on.
                    uow.subscriptions.record(
                        Delivery(
                            issue_id=issue.id,
                            subscription_id=subscription.id,
                            sent_at=self._clock.now(),
                        )
                    )
                    with contextlib.suppress(ForeignKeyViolationError, UniqueViolationError):
                        await uow.commit()
        _logger.info("newsletter.issue.sent", number=issue.number, mails=sent)
