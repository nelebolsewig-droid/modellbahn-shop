"""SQLAlchemy implementations of the identity repositories and unit of work.

Repositories only read and stage changes; committing is the unit of work's job.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import Select, delete, exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from modellbahn.modules.identity.domain.model import (
    Account,
    AccountKind,
    AccountToken,
    LoginSession,
    TokenPurpose,
)
from modellbahn.modules.identity.infrastructure.mapping import start_mappers
from modellbahn.modules.identity.infrastructure.tables import account_tokens, accounts, sessions
from modellbahn.platform.uow import UnitOfWork


def _locked[*Ts](statement: Select[*Ts], for_update: bool) -> Select[*Ts]:
    if not for_update:
        return statement
    # Refresh an object already in the identity map with the row we now hold locked.
    return statement.with_for_update().execution_options(populate_existing=True)


class SqlAccountRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, account_id: UUID, *, for_update: bool = False) -> Account | None:
        statement = _locked(select(Account).where(accounts.c.id == account_id), for_update)
        return (await self._session.execute(statement)).scalar_one_or_none()

    async def get_by_email(
        self, kind: AccountKind, email: str, *, for_update: bool = False
    ) -> Account | None:
        # The column is citext, so this comparison ignores case.
        statement = _locked(
            select(Account).where(accounts.c.kind == kind, accounts.c.email == email), for_update
        )
        return (await self._session.execute(statement)).scalar_one_or_none()

    def add(self, account: Account) -> None:
        self._session.add(account)


class SqlLoginSessionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, token_hash: str) -> LoginSession | None:
        return await self._session.get(LoginSession, token_hash)

    def add(self, session: LoginSession) -> None:
        self._session.add(session)

    async def delete(self, token_hash: str) -> None:
        await self._session.execute(delete(LoginSession).where(sessions.c.token_hash == token_hash))

    async def delete_for_account(
        self, account_id: UUID, *, except_token_hash: str | None = None
    ) -> None:
        statement = delete(LoginSession).where(sessions.c.account_id == account_id)
        if except_token_hash is not None:
            statement = statement.where(sessions.c.token_hash != except_token_hash)
        await self._session.execute(statement)

    async def delete_expired_for_account(self, account_id: UUID, now: datetime) -> None:
        await self._session.execute(
            delete(LoginSession).where(
                sessions.c.account_id == account_id, sessions.c.expires_at <= now
            )
        )


class SqlAccountTokenRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, token_hash: str, *, for_update: bool = False) -> AccountToken | None:
        statement = _locked(
            select(AccountToken).where(account_tokens.c.token_hash == token_hash), for_update
        )
        return (await self._session.execute(statement)).scalar_one_or_none()

    def add(self, token: AccountToken) -> None:
        self._session.add(token)

    async def exists_for_source_event(self, event_id: UUID) -> bool:
        statement = select(exists().where(account_tokens.c.source_event_id == event_id))
        return bool((await self._session.execute(statement)).scalar())

    async def delete_unused(self, account_id: UUID, purpose: TokenPurpose) -> None:
        await self._session.execute(
            delete(AccountToken).where(
                account_tokens.c.account_id == account_id,
                account_tokens.c.purpose == purpose,
                account_tokens.c.used_at.is_(None),
            )
        )

    async def delete_for_account(self, account_id: UUID) -> None:
        await self._session.execute(
            delete(AccountToken).where(account_tokens.c.account_id == account_id)
        )


class SqlIdentityUnitOfWork(UnitOfWork):
    """Unit of work with the identity repositories attached."""

    accounts: SqlAccountRepository
    sessions: SqlLoginSessionRepository
    tokens: SqlAccountTokenRepository

    def _attach(self, session: AsyncSession) -> None:
        start_mappers()
        self.accounts = SqlAccountRepository(session)
        self.sessions = SqlLoginSessionRepository(session)
        self.tokens = SqlAccountTokenRepository(session)
