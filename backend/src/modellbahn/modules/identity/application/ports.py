"""What the identity use cases need from the outside world, as protocols.

The infrastructure layer implements them; tests may substitute their own.
"""

from datetime import datetime
from types import TracebackType
from typing import Protocol, Self
from uuid import UUID

from modellbahn.modules.identity.domain.model import (
    Account,
    AccountKind,
    AccountToken,
    LoginSession,
    TokenPurpose,
)
from modellbahn.platform.events import DomainEvent


class AccountRepository(Protocol):
    async def get(self, account_id: UUID, *, for_update: bool = False) -> Account | None:
        """The account with this id. ``for_update`` locks the row until commit."""
        ...

    async def get_by_email(
        self, kind: AccountKind, email: str, *, for_update: bool = False
    ) -> Account | None:
        """The account of ``kind`` with this address, compared case-insensitively."""
        ...

    def add(self, account: Account) -> None: ...


class LoginSessionRepository(Protocol):
    async def get(self, token_hash: str) -> LoginSession | None: ...

    def add(self, session: LoginSession) -> None: ...

    async def delete(self, token_hash: str) -> None: ...

    async def delete_for_account(
        self, account_id: UUID, *, except_token_hash: str | None = None
    ) -> None:
        """End every session of the account, optionally except the current one."""
        ...

    async def delete_expired_for_account(self, account_id: UUID, now: datetime) -> None: ...


class AccountTokenRepository(Protocol):
    async def get(self, token_hash: str, *, for_update: bool = False) -> AccountToken | None: ...

    def add(self, token: AccountToken) -> None: ...

    async def exists_for_source_event(self, event_id: UUID) -> bool:
        """True if a token was already issued because of this outbox event."""
        ...

    async def delete_unused(self, account_id: UUID, purpose: TokenPurpose) -> None:
        """Invalidate the account's outstanding tokens of ``purpose``."""
        ...

    async def delete_for_account(self, account_id: UUID) -> None: ...


class IdentityUnitOfWork(Protocol):
    """One transaction over the identity repositories (see ``platform.uow``)."""

    @property
    def accounts(self) -> AccountRepository: ...

    @property
    def sessions(self) -> LoginSessionRepository: ...

    @property
    def tokens(self) -> AccountTokenRepository: ...

    async def __aenter__(self) -> Self: ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...

    def publish(self, *events: DomainEvent) -> None: ...

    async def flush(self) -> None: ...

    async def commit(self) -> None: ...


class PasswordHasher(Protocol):
    async def hash(self, password: str) -> str: ...

    async def verify(self, password_hash: str, password: str) -> bool: ...

    async def dummy_verify(self, password: str) -> None:
        """Take as long as :meth:`verify` (for unknown or locked accounts)."""
        ...

    def needs_rehash(self, password_hash: str) -> bool: ...
