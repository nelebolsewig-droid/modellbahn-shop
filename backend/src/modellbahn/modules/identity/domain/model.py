"""The identity model: accounts, login sessions and one-time tokens.

Plain dataclasses without any framework. SQLAlchemy maps them imperatively (see
``infrastructure/mapping.py``), so they are tested here without a database. Every
method that depends on time takes ``now`` explicitly.
"""

import unicodedata
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Final
from uuid import UUID

from modellbahn.modules.identity.domain.errors import (
    InvalidDisplayNameError,
    InvalidTokenError,
    PasswordPolicyViolationError,
    PasswordRule,
)
from modellbahn.modules.identity.domain.events import (
    AccountDeleted,
    CustomerRegistered,
    EmailVerified,
    PasswordChanged,
    PasswordResetRequested,
    RegistrationAttemptedForExistingAccount,
    VerificationMailRequested,
)
from modellbahn.platform.events import DomainEvent
from modellbahn.platform.ids import new_id

PASSWORD_MIN_LENGTH: Final = 10
PASSWORD_MAX_LENGTH: Final = 256
DISPLAY_NAME_MAX_LENGTH: Final = 80

LOCKOUT_THRESHOLD: Final = 5
LOCKOUT_BASE_DURATION: Final = timedelta(minutes=15)
LOCKOUT_MAX_DURATION: Final = timedelta(hours=24)
# failed_login_count is a smallint; the lock duration stops growing long before this.
_MAX_FAILED_LOGIN_COUNT: Final = 32_767

CUSTOMER_SESSION_LIFETIME: Final = timedelta(days=30)
STAFF_SESSION_LIFETIME: Final = timedelta(hours=12)
SESSION_TOUCH_INTERVAL: Final = timedelta(minutes=5)
USER_AGENT_MAX_LENGTH: Final = 512

VERIFY_EMAIL_TOKEN_LIFETIME: Final = timedelta(hours=24)
RESET_PASSWORD_TOKEN_LIFETIME: Final = timedelta(hours=1)

DELETED_DISPLAY_NAME: Final = "Gelöschtes Konto"
# Not an Argon2 hash, so no password can ever match it.
UNUSABLE_PASSWORD_HASH: Final = "!unusable"  # noqa: S105

# Bidirectional overrides and isolates can make a name display as something else.
_BIDI_CONTROLS: Final = frozenset("\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069")


class AccountKind(StrEnum):
    """Staff and customers share one table but never one session (see ``LoginSession``)."""

    STAFF = "staff"
    CUSTOMER = "customer"


class StaffRole(StrEnum):
    OWNER = "owner"
    STAFF = "staff"
    PACKER = "packer"


class AccountStatus(StrEnum):
    ACTIVE = "active"
    DELETED = "deleted"


class TokenPurpose(StrEnum):
    VERIFY_EMAIL = "verify_email"
    RESET_PASSWORD = "reset_password"  # noqa: S105


def check_password_policy(password: str, *, email: str) -> None:
    """Raise :class:`PasswordPolicyViolationError` unless ``password`` may be used.

    10 to 256 characters and not the e-mail address itself. Length beats composition
    rules; the upper bound only keeps hashing cheap to request.
    """
    if len(password) < PASSWORD_MIN_LENGTH:
        raise PasswordPolicyViolationError(PasswordRule.TOO_SHORT)
    if len(password) > PASSWORD_MAX_LENGTH:
        raise PasswordPolicyViolationError(PasswordRule.TOO_LONG)
    if password.casefold() == email.casefold():
        raise PasswordPolicyViolationError(PasswordRule.EQUALS_EMAIL)


def normalize_display_name(value: str) -> str:
    """Collapse whitespace and validate; raise :class:`InvalidDisplayNameError` if unusable."""
    name = " ".join(value.split())
    if not 1 <= len(name) <= DISPLAY_NAME_MAX_LENGTH:
        raise InvalidDisplayNameError(
            f"display name must have 1 to {DISPLAY_NAME_MAX_LENGTH} characters"
        )
    if any(unicodedata.category(char) == "Cc" or char in _BIDI_CONTROLS for char in name):
        raise InvalidDisplayNameError("display name contains control characters")
    return name


def lockout_duration(failed_login_count: int) -> timedelta | None:
    """How long to lock an account after ``failed_login_count`` consecutive failures.

    Every fifth failure in a row locks the account, each time twice as long as the
    time before: 15 min, 30 min, 1 h, ... capped at 24 h. ``None`` means no lock.
    """
    if failed_login_count < LOCKOUT_THRESHOLD or failed_login_count % LOCKOUT_THRESHOLD:
        return None
    lockouts = failed_login_count // LOCKOUT_THRESHOLD
    # Beyond 2^7 the cap applies anyway; bounding the exponent avoids huge numbers.
    return min(LOCKOUT_BASE_DURATION * (1 << min(lockouts - 1, 16)), LOCKOUT_MAX_DURATION)


def anonymised_email(account_id: UUID) -> str:
    """The address a deleted account keeps; unique and never deliverable."""
    return f"deleted+{account_id}@invalid.local"


@dataclass(eq=False, kw_only=True)
class Account:
    """A staff member or customer. The aggregate root of the identity module.

    The e-mail address is unique per kind (case-insensitive). Staff accounts have a
    role, customer accounts never do. Deleting anonymises the row instead of removing
    it, because orders will keep referring to it.
    """

    id: UUID
    kind: AccountKind
    email: str
    display_name: str
    password_hash: str
    role: StaffRole | None
    status: AccountStatus
    email_verified_at: datetime | None
    failed_login_count: int
    locked_until: datetime | None
    last_login_at: datetime | None
    created_at: datetime
    updated_at: datetime
    # Maintained by the persistence layer for optimistic locking.
    version: int = 1

    @classmethod
    def register_customer(
        cls, *, email: str, display_name: str, password_hash: str, now: datetime
    ) -> tuple["Account", CustomerRegistered]:
        account = cls._new(
            kind=AccountKind.CUSTOMER,
            email=email,
            display_name=display_name,
            password_hash=password_hash,
            role=None,
            now=now,
        )
        event = CustomerRegistered(
            aggregate_id=account.id, occurred_at=now, display_name=account.display_name
        )
        return account, event

    @classmethod
    def create_staff(
        cls, *, email: str, display_name: str, role: StaffRole, password_hash: str, now: datetime
    ) -> "Account":
        return cls._new(
            kind=AccountKind.STAFF,
            email=email,
            display_name=display_name,
            password_hash=password_hash,
            role=role,
            now=now,
        )

    @classmethod
    def _new(
        cls,
        *,
        kind: AccountKind,
        email: str,
        display_name: str,
        password_hash: str,
        role: StaffRole | None,
        now: datetime,
    ) -> "Account":
        return cls(
            id=new_id(),
            kind=kind,
            email=email,
            display_name=normalize_display_name(display_name),
            password_hash=password_hash,
            role=role,
            status=AccountStatus.ACTIVE,
            email_verified_at=None,
            failed_login_count=0,
            locked_until=None,
            last_login_at=None,
            created_at=now,
            updated_at=now,
        )

    @property
    def is_active(self) -> bool:
        return self.status is AccountStatus.ACTIVE

    @property
    def is_customer(self) -> bool:
        return self.kind is AccountKind.CUSTOMER

    @property
    def email_verified(self) -> bool:
        return self.email_verified_at is not None

    @property
    def needs_email_verification(self) -> bool:
        """Only customers verify their address; staff accounts are set up by the owner."""
        return self.is_customer and not self.email_verified

    def is_locked(self, now: datetime) -> bool:
        return self.locked_until is not None and now < self.locked_until

    # --- Login -----------------------------------------------------------------------

    def record_failed_login(self, now: datetime) -> None:
        """Count a wrong password; every fifth failure in a row locks the account."""
        self.failed_login_count = min(self.failed_login_count + 1, _MAX_FAILED_LOGIN_COUNT)
        duration = lockout_duration(self.failed_login_count)
        if duration is not None:
            self.locked_until = now + duration
        self.updated_at = now

    def record_successful_login(self, now: datetime) -> None:
        self.failed_login_count = 0
        self.locked_until = None
        self.last_login_at = now
        self.updated_at = now

    def record_correct_password(self, now: datetime) -> None:
        """The password was right, even if the login cannot complete (unverified address)."""
        if self.failed_login_count or self.locked_until is not None:
            self.failed_login_count = 0
            self.locked_until = None
            self.updated_at = now

    # --- Changes by the account holder -----------------------------------------------

    def rename(self, display_name: str, now: datetime) -> None:
        self.display_name = normalize_display_name(display_name)
        self.updated_at = now

    def change_password(self, password_hash: str, now: datetime) -> PasswordChanged:
        self.password_hash = password_hash
        self.updated_at = now
        return PasswordChanged(aggregate_id=self.id, occurred_at=now)

    def rehash_password(self, password_hash: str, now: datetime) -> None:
        """Store the same password hashed with current parameters (no event)."""
        self.password_hash = password_hash
        self.updated_at = now

    def reset_password(self, password_hash: str, now: datetime) -> list[DomainEvent]:
        """Set a new password via an e-mailed reset link.

        Receiving the link proves control of the address, so an unverified address
        counts as verified afterwards, and a lock from failed logins is lifted.
        """
        events: list[DomainEvent] = [self.change_password(password_hash, now)]
        verified = self.verify_email(now)
        if verified is not None:
            events.append(verified)
        self.failed_login_count = 0
        self.locked_until = None
        return events

    def verify_email(self, now: datetime) -> EmailVerified | None:
        """Mark the address as verified; returns the event only on the first time."""
        if self.email_verified_at is not None:
            return None
        self.email_verified_at = now
        self.updated_at = now
        return EmailVerified(aggregate_id=self.id, occurred_at=now, display_name=self.display_name)

    def delete(self, now: datetime) -> AccountDeleted:
        """Anonymise the account (GDPR). The row stays for orders that reference it."""
        self.status = AccountStatus.DELETED
        self.email = anonymised_email(self.id)
        self.display_name = DELETED_DISPLAY_NAME
        self.password_hash = UNUSABLE_PASSWORD_HASH
        self.failed_login_count = 0
        self.locked_until = None
        self.updated_at = now
        return AccountDeleted(aggregate_id=self.id, occurred_at=now)

    # --- Requests that end in an e-mail ----------------------------------------------

    def note_registration_attempt(self, now: datetime) -> RegistrationAttemptedForExistingAccount:
        return RegistrationAttemptedForExistingAccount(aggregate_id=self.id, occurred_at=now)

    def request_verification_mail(self, now: datetime) -> VerificationMailRequested | None:
        if not (self.is_active and self.needs_email_verification):
            return None
        return VerificationMailRequested(aggregate_id=self.id, occurred_at=now)

    def request_password_reset(self, now: datetime) -> PasswordResetRequested | None:
        if not (self.is_active and self.is_customer):
            return None
        return PasswordResetRequested(aggregate_id=self.id, occurred_at=now)


@dataclass(eq=False, kw_only=True)
class LoginSession:
    """A login, identified by the SHA-256 hash of the token in the browser's cookie.

    A session belongs to one area (``kind``): a customer session never opens the
    admin area and vice versa. Lifetimes are fixed, not sliding.
    """

    token_hash: str
    account_id: UUID
    kind: AccountKind
    created_at: datetime
    expires_at: datetime
    last_seen_at: datetime
    user_agent: str | None

    @classmethod
    def start(
        cls, *, account: Account, token_hash: str, now: datetime, user_agent: str | None
    ) -> "LoginSession":
        lifetime = (
            CUSTOMER_SESSION_LIFETIME
            if account.kind is AccountKind.CUSTOMER
            else STAFF_SESSION_LIFETIME
        )
        return cls(
            token_hash=token_hash,
            account_id=account.id,
            kind=account.kind,
            created_at=now,
            expires_at=now + lifetime,
            last_seen_at=now,
            user_agent=user_agent[:USER_AGENT_MAX_LENGTH] if user_agent else None,
        )

    def is_expired(self, now: datetime) -> bool:
        return now >= self.expires_at

    def touch(self, now: datetime) -> bool:
        """Record activity, at most every five minutes; True if something changed."""
        if now - self.last_seen_at < SESSION_TOUCH_INTERVAL:
            return False
        self.last_seen_at = now
        return True


@dataclass(eq=False, kw_only=True)
class AccountToken:
    """A one-time token sent by e-mail; only its SHA-256 hash is stored.

    ``source_event_id`` names the outbox event that caused the token, which makes
    the mail handlers idempotent.
    """

    token_hash: str
    account_id: UUID
    purpose: TokenPurpose
    created_at: datetime
    expires_at: datetime
    used_at: datetime | None
    source_event_id: UUID | None

    @classmethod
    def issue(
        cls,
        *,
        token_hash: str,
        account_id: UUID,
        purpose: TokenPurpose,
        now: datetime,
        source_event_id: UUID | None,
    ) -> "AccountToken":
        lifetime = (
            VERIFY_EMAIL_TOKEN_LIFETIME
            if purpose is TokenPurpose.VERIFY_EMAIL
            else RESET_PASSWORD_TOKEN_LIFETIME
        )
        return cls(
            token_hash=token_hash,
            account_id=account_id,
            purpose=purpose,
            created_at=now,
            expires_at=now + lifetime,
            used_at=None,
            source_event_id=source_event_id,
        )

    def redeem(self, purpose: TokenPurpose, now: datetime) -> None:
        """Use the token up; raise :class:`InvalidTokenError` if that is not possible."""
        if self.purpose is not purpose or self.used_at is not None or now >= self.expires_at:
            raise InvalidTokenError
        self.used_at = now
