"""Outbox event handlers of the identity module; the worker runs them.

``identity.account.email_verified`` and ``identity.account.deleted`` need nothing
from this module: the dispatcher marks events without handlers as published (and
still pushes ``email_verified`` to the admin area). Other modules subscribe to them.
"""

from collections.abc import Callable, Sequence

import structlog

from modellbahn.modules.identity.application import mails
from modellbahn.modules.identity.application.services import UnitOfWorkFactory
from modellbahn.modules.identity.domain.events import (
    CustomerRegistered,
    PasswordChanged,
    PasswordResetRequested,
    RegistrationAttemptedForExistingAccount,
    VerificationMailRequested,
)
from modellbahn.modules.identity.domain.model import Account, AccountToken, TokenPurpose
from modellbahn.platform.clock import Clock
from modellbahn.platform.events import DomainEvent
from modellbahn.platform.mail import MailContent, Mailer, compose
from modellbahn.platform.outbox import HandlerRegistry
from modellbahn.platform.security import generate_token, hash_token
from modellbahn.platform.uow import UniqueViolationError

_logger = structlog.get_logger(__name__)

type TokenMail = Callable[[Account, str], MailContent]


class IdentityMailHandlers:
    """Send the identity e-mails. Delivery is at least once, so every handler is idempotent.

    Handlers that issue a token insert the token row (unique ``source_event_id`` =
    event id) and commit it only after the mail went out. A retry therefore finds the
    row and stops; a mail that failed leaves no row and is retried with a new token.
    The raw token exists only in this process and in the mail, never in the database,
    the logs or the outbox. Plain notices may in rare cases be sent twice.
    """

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
        registry.register(CustomerRegistered, self.send_verification_mail)
        registry.register(VerificationMailRequested, self.send_verification_mail)
        registry.register(RegistrationAttemptedForExistingAccount, self.send_existing_account_mail)
        registry.register(PasswordResetRequested, self.send_password_reset_mail)
        registry.register(PasswordChanged, self.send_password_changed_mail)

    async def send_verification_mail(
        self, event: CustomerRegistered | VerificationMailRequested
    ) -> None:
        def content(account: Account, token: str) -> MailContent:
            return mails.verification_mail(
                account, base_url=self._base_url, token=token, shop_name=self._shop_name
            )

        await self._send_with_token(
            event,
            purpose=TokenPurpose.VERIFY_EMAIL,
            eligible=lambda account: account.is_active and account.needs_email_verification,
            content=content,
        )

    async def send_password_reset_mail(self, event: PasswordResetRequested) -> None:
        def content(account: Account, token: str) -> MailContent:
            return mails.password_reset_mail(account, base_url=self._base_url, token=token)

        await self._send_with_token(
            event,
            purpose=TokenPurpose.RESET_PASSWORD,
            eligible=lambda account: account.is_active and account.is_customer,
            content=content,
        )

    async def send_existing_account_mail(
        self, event: RegistrationAttemptedForExistingAccount
    ) -> None:
        account = await self._active_account(event)
        if account is not None:
            content = mails.existing_account_mail(
                account, base_url=self._base_url, shop_name=self._shop_name
            )
            await self._send(event, account, content)

    async def send_password_changed_mail(self, event: PasswordChanged) -> None:
        account = await self._active_account(event)
        if account is not None:
            content = mails.password_changed_mail(
                account, base_url=self._base_url, shop_name=self._shop_name
            )
            await self._send(event, account, content)

    async def _send_with_token(
        self,
        event: DomainEvent,
        *,
        purpose: TokenPurpose,
        eligible: Callable[[Account], bool],
        content: TokenMail,
    ) -> None:
        async with self._uow() as uow:
            if await uow.tokens.exists_for_source_event(event.event_id):
                return
            account = await uow.accounts.get(event.aggregate_id)
            if account is None or not eligible(account):
                _logger.info("identity.mail.skipped", event_id=str(event.event_id))
                return
            token = generate_token()
            uow.tokens.add(
                AccountToken.issue(
                    token_hash=hash_token(token),
                    account_id=account.id,
                    purpose=purpose,
                    now=self._clock.now(),
                    source_event_id=event.event_id,
                )
            )
            try:
                await uow.flush()
            except UniqueViolationError:
                # Another run of this handler got there first and sends the mail.
                return
            await self._send(event, account, content(account, token))
            await uow.commit()

    async def _active_account(self, event: DomainEvent) -> Account | None:
        async with self._uow() as uow:
            account = await uow.accounts.get(event.aggregate_id)
        if account is None or not account.is_active:
            _logger.info("identity.mail.skipped", event_id=str(event.event_id))
            return None
        return account

    async def _send(self, event: DomainEvent, account: Account, content: MailContent) -> None:
        await self._mailer.send(
            compose(content, to=account.email, shop_name=self._shop_name, sender=self._sender)
        )
        _logger.info(
            "identity.mail.sent",
            event_id=str(event.event_id),
            event_type=event.event_type,
            account_id=str(account.id),
        )
