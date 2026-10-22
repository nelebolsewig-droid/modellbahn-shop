"""Identity use cases: registration, verification, login, sessions, passwords, deletion.

Every public method runs in its own unit of work. Answers that could reveal whether
an address has an account (registration, resend, reset) are identical either way.
Registration also matches its timing (it hashes the password either way); resend
and reset leave their timing to the API, which answers before running them.
Requests that send a mail are throttled per address (``mail_request_allowed``).
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from modellbahn.modules.identity.application.ports import IdentityUnitOfWork, PasswordHasher
from modellbahn.modules.identity.domain.errors import (
    AccountAlreadyExistsError,
    AccountNotFoundError,
    EmailNotVerifiedError,
    InvalidCredentialsError,
    InvalidPasswordError,
    InvalidTokenError,
    NotAuthenticatedError,
)
from modellbahn.modules.identity.domain.events import MAIL_REQUEST_EVENT_TYPES
from modellbahn.modules.identity.domain.model import (
    DELETED_DISPLAY_NAME,
    MAIL_REQUEST_WINDOW,
    Account,
    AccountKind,
    LoginSession,
    StaffRole,
    TokenPurpose,
    check_password_policy,
    mail_request_allowed,
    normalize_display_name,
)
from modellbahn.platform.clock import Clock
from modellbahn.platform.security import generate_token, hash_token
from modellbahn.platform.uow import UniqueViolationError

type UnitOfWorkFactory = Callable[[], IdentityUnitOfWork]


@dataclass(frozen=True, slots=True)
class StartedSession:
    """A new login. ``token`` goes into the cookie and is never stored."""

    account: Account
    token: str
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class Authentication:
    """The account behind a valid session cookie."""

    account: Account
    session_token_hash: str


class IdentityService:
    """The identity module's use cases, independent of HTTP."""

    def __init__(
        self, *, uow_factory: UnitOfWorkFactory, hasher: PasswordHasher, clock: Clock
    ) -> None:
        self._uow = uow_factory
        self._hasher = hasher
        self._clock = clock

    # --- Registration and verification -----------------------------------------------

    async def register_customer(self, *, email: str, password: str, display_name: str) -> None:
        """Create a customer account, or tell the owner of the address by mail.

        The caller cannot tell the two outcomes apart; both end in an e-mail.
        """
        check_password_policy(password, email=email)
        display_name = normalize_display_name(display_name)
        # Hash even when the address is taken, so both answers take equally long.
        password_hash = await self._hasher.hash(password)
        try:
            await self._register_customer(email, display_name, password_hash)
        except UniqueViolationError:
            # A concurrent registration with the same address won; now it exists.
            await self._register_customer(email, display_name, password_hash)

    async def _register_customer(self, email: str, display_name: str, password_hash: str) -> None:
        async with self._uow() as uow:
            now = self._clock.now()
            existing = await uow.accounts.get_by_email(AccountKind.CUSTOMER, email)
            if existing is not None:
                if await self._may_send_mail(uow, existing, now):
                    uow.publish(existing.note_registration_attempt(now))
            else:
                account, registered = Account.register_customer(
                    email=email, display_name=display_name, password_hash=password_hash, now=now
                )
                uow.accounts.add(account)
                uow.publish(registered)
            await uow.commit()

    async def verify_email(
        self, *, token: str, password: str, user_agent: str | None
    ) -> StartedSession:
        """Redeem a verification token: the address counts as verified and a session starts.

        The link alone is not enough; the password chosen at registration is required
        too. Otherwise someone could register with another person's address and a
        password of their own: as soon as that person clicked the link out of
        curiosity, the stranger would own a verified account with that address (and,
        from step 4 on, see its guest orders). A wrong password leaves the token
        unused; the owner of the address who never registered uses the reset instead,
        which replaces the stranger's password.
        """
        async with self._uow() as uow:
            now = self._clock.now()
            account_token = await uow.tokens.get(hash_token(token), for_update=True)
            if account_token is None:
                raise InvalidTokenError
            account_token.check(TokenPurpose.VERIFY_EMAIL, now)
            account = await uow.accounts.get(account_token.account_id, for_update=True)
            if account is None or not account.is_active or not account.is_customer:
                raise InvalidTokenError
            await self._confirm_password(uow, account, password, now)
            account_token.redeem(TokenPurpose.VERIFY_EMAIL, now)
            verified = account.verify_email(now)
            if verified is not None:
                uow.publish(verified)
            # Each verification link also logs in; the others must not keep doing so.
            await uow.tokens.delete_unused(account.id, TokenPurpose.VERIFY_EMAIL)
            started = self._start_session(uow, account, now, user_agent)
            await uow.commit()
        return started

    async def request_verification_mail(self, *, email: str) -> None:
        """Send a new verification mail if the address belongs to an unverified customer."""
        async with self._uow() as uow:
            now = self._clock.now()
            account = await uow.accounts.get_by_email(AccountKind.CUSTOMER, email)
            event = account.request_verification_mail(now) if account else None
            if account and event is not None and await self._may_send_mail(uow, account, now):
                uow.publish(event)
                await uow.commit()

    # --- Sessions --------------------------------------------------------------------

    async def login(
        self, *, kind: AccountKind, email: str, password: str, user_agent: str | None
    ) -> StartedSession:
        """Check the credentials for the area ``kind`` and start a session.

        Unknown addresses, wrong passwords and locked accounts all raise
        :class:`InvalidCredentialsError` after a full password verification.
        """
        async with self._uow() as uow:
            now = self._clock.now()
            account = await uow.accounts.get_by_email(kind, email, for_update=True)
            if account is None or not account.is_active or account.is_locked(now):
                await self._hasher.dummy_verify(password)
                raise InvalidCredentialsError
            if not await self._hasher.verify(account.password_hash, password):
                account.record_failed_login(now)
                await uow.commit()
                raise InvalidCredentialsError
            if account.needs_email_verification:
                account.record_correct_password(now)
                await uow.commit()
                raise EmailNotVerifiedError
            if self._hasher.needs_rehash(account.password_hash):
                account.rehash_password(await self._hasher.hash(password), now)
            await uow.sessions.delete_expired_for_account(account.id, now)
            started = self._start_session(uow, account, now, user_agent)
            await uow.commit()
        return started

    async def authenticate(self, *, kind: AccountKind, token: str) -> Authentication:
        """The account of a session token, if the session is valid for the area ``kind``."""
        token_hash = hash_token(token)
        async with self._uow() as uow:
            now = self._clock.now()
            session = await uow.sessions.get(token_hash)
            if session is None or session.kind is not kind:
                raise NotAuthenticatedError
            if session.is_expired(now):
                await uow.sessions.delete(token_hash)
                await uow.commit()
                raise NotAuthenticatedError
            account = await uow.accounts.get(session.account_id)
            if account is None or not account.is_active:
                raise NotAuthenticatedError
            if session.touch(now):
                await uow.commit()
        return Authentication(account=account, session_token_hash=token_hash)

    async def logout(self, *, kind: AccountKind, token: str) -> None:
        """End the session of ``token`` if it belongs to the area ``kind``. Idempotent."""
        token_hash = hash_token(token)
        async with self._uow() as uow:
            session = await uow.sessions.get(token_hash)
            if session is not None and session.kind is kind:
                await uow.sessions.delete(token_hash)
                await uow.commit()

    # --- Account maintenance ---------------------------------------------------------

    async def rename(self, *, account_id: UUID, display_name: str) -> Account:
        async with self._uow() as uow:
            account = await self._load_active(uow, account_id)
            account.rename(display_name, self._clock.now())
            await uow.commit()
        return account

    async def change_password(
        self,
        *,
        account_id: UUID,
        session_token_hash: str,
        current_password: str,
        new_password: str,
    ) -> None:
        """Replace the password; every other session of the account ends."""
        async with self._uow() as uow:
            now = self._clock.now()
            account = await self._load_active(uow, account_id)
            check_password_policy(new_password, email=account.email)
            await self._confirm_password(uow, account, current_password, now)
            changed = account.change_password(await self._hasher.hash(new_password), now)
            await uow.sessions.delete_for_account(account.id, except_token_hash=session_token_hash)
            await uow.tokens.delete_unused(account.id, TokenPurpose.RESET_PASSWORD)
            uow.publish(changed)
            await uow.commit()

    async def request_password_reset(self, *, email: str) -> None:
        """Send a reset link if the address belongs to an active customer."""
        async with self._uow() as uow:
            now = self._clock.now()
            account = await uow.accounts.get_by_email(AccountKind.CUSTOMER, email)
            event = account.request_password_reset(now) if account else None
            if account and event is not None and await self._may_send_mail(uow, account, now):
                uow.publish(event)
                await uow.commit()

    async def reset_password(self, *, token: str, new_password: str) -> None:
        """Set a new password with a reset token; every session of the account ends."""
        async with self._uow() as uow:
            now = self._clock.now()
            account_token = await uow.tokens.get(hash_token(token), for_update=True)
            if account_token is None:
                raise InvalidTokenError
            account_token.redeem(TokenPurpose.RESET_PASSWORD, now)
            account = await uow.accounts.get(account_token.account_id, for_update=True)
            if account is None or not account.is_active or not account.is_customer:
                raise InvalidTokenError
            check_password_policy(new_password, email=account.email)
            events = account.reset_password(await self._hasher.hash(new_password), now)
            await uow.sessions.delete_for_account(account.id)
            # Older reset links die with this one; the address is verified now, too.
            await uow.tokens.delete_unused(account.id, TokenPurpose.RESET_PASSWORD)
            await uow.tokens.delete_unused(account.id, TokenPurpose.VERIFY_EMAIL)
            uow.publish(*events)
            await uow.commit()

    async def delete_account(self, *, account_id: UUID, password: str) -> None:
        """Anonymise the account after confirming the password; all sessions end."""
        async with self._uow() as uow:
            now = self._clock.now()
            account = await self._load_active(uow, account_id)
            await self._confirm_password(uow, account, password, now)
            deleted = account.delete(now)
            await uow.sessions.delete_for_account(account.id)
            await uow.tokens.delete_for_account(account.id)
            # The outbox keeps published events for the admin feed's replay; the name
            # must leave them in the same transaction as it leaves the account.
            await uow.redact_events(account.id, {"display_name": DELETED_DISPLAY_NAME})
            uow.publish(deleted)
            await uow.commit()

    # --- Staff -----------------------------------------------------------------------

    async def create_staff(
        self, *, email: str, display_name: str, role: StaffRole, password: str
    ) -> Account:
        """Create a staff account (used by the CLI; there is no self-registration)."""
        check_password_policy(password, email=email)
        display_name = normalize_display_name(display_name)
        password_hash = await self._hasher.hash(password)
        async with self._uow() as uow:
            if await uow.accounts.get_by_email(AccountKind.STAFF, email) is not None:
                raise AccountAlreadyExistsError
            account = Account.create_staff(
                email=email,
                display_name=display_name,
                role=role,
                password_hash=password_hash,
                now=self._clock.now(),
            )
            uow.accounts.add(account)
            try:
                await uow.commit()
            except UniqueViolationError as exc:
                raise AccountAlreadyExistsError from exc
        return account

    async def unlock_staff(self, *, email: str) -> None:
        """Lift the login lock of a staff account (used by the CLI on the server)."""
        async with self._uow() as uow:
            account = await uow.accounts.get_by_email(AccountKind.STAFF, email, for_update=True)
            if account is None or not account.is_active:
                raise AccountNotFoundError
            account.unlock(self._clock.now())
            await uow.commit()

    # --- Helpers ---------------------------------------------------------------------

    async def _may_send_mail(
        self, uow: IdentityUnitOfWork, account: Account, now: datetime
    ) -> bool:
        recent = await uow.count_recent_events(
            account.id, MAIL_REQUEST_EVENT_TYPES, since=now - MAIL_REQUEST_WINDOW
        )
        return mail_request_allowed(recent)

    def _start_session(
        self, uow: IdentityUnitOfWork, account: Account, now: datetime, user_agent: str | None
    ) -> StartedSession:
        token = generate_token()
        session = LoginSession.start(
            account=account, token_hash=hash_token(token), now=now, user_agent=user_agent
        )
        uow.sessions.add(session)
        account.record_successful_login(now)
        return StartedSession(account=account, token=token, expires_at=session.expires_at)

    async def _load_active(self, uow: IdentityUnitOfWork, account_id: UUID) -> Account:
        account = await uow.accounts.get(account_id, for_update=True)
        if account is None or not account.is_active:
            raise NotAuthenticatedError
        return account

    async def _confirm_password(
        self, uow: IdentityUnitOfWork, account: Account, password: str, now: datetime
    ) -> None:
        """Check the password of a logged-in account; failures count towards the lockout."""
        if account.is_locked(now):
            await self._hasher.dummy_verify(password)
            raise InvalidPasswordError
        if not await self._hasher.verify(account.password_hash, password):
            account.record_failed_login(now)
            await uow.commit()
            raise InvalidPasswordError
        account.record_correct_password(now)
