"""Unit of work, outbox writes, repositories and the database constraints behind them."""

from datetime import timedelta
from uuid import uuid4

import asyncpg
import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from modellbahn.modules.identity.application.services import UnitOfWorkFactory
from modellbahn.modules.identity.contracts import AccountKind, get_account_summary
from modellbahn.modules.identity.domain.model import (
    Account,
    AccountToken,
    LoginSession,
    StaffRole,
    TokenPurpose,
)
from modellbahn.modules.identity.infrastructure.repositories import SqlIdentityUnitOfWork
from modellbahn.platform.config import Settings
from modellbahn.platform.db import asyncpg_dsn
from modellbahn.platform.events import EventRegistry
from modellbahn.platform.outbox import outbox_table
from modellbahn.platform.security import hash_token
from modellbahn.platform.uow import ConcurrentUpdateError, UniqueViolationError, UnitOfWork
from tests.support import NOW, SampleHappened, eventually, sample


def new_customer(email: str = "kunde@example.com") -> Account:
    account, _ = Account.register_customer(
        email=email, display_name="Erika", password_hash="hash", now=NOW
    )
    return account


async def outbox_rows(engine: AsyncEngine) -> list[dict[str, object]]:
    async with engine.connect() as connection:
        rows = await connection.execute(select(outbox_table).order_by(outbox_table.c.id))
        return [dict(row._mapping) for row in rows]


class TestUnitOfWork:
    async def test_commit_writes_state_and_events_in_one_transaction(
        self, uow_factory: UnitOfWorkFactory, engine: AsyncEngine
    ) -> None:
        account, registered = Account.register_customer(
            email="kunde@example.com", display_name="Erika", password_hash="hash", now=NOW
        )
        async with uow_factory() as uow:
            uow.accounts.add(account)
            uow.publish(registered)
            await uow.commit()

        (row,) = await outbox_rows(engine)
        assert row["id"] == registered.event_id
        assert row["event_type"] == "identity.customer.registered"
        assert row["aggregate_type"] == "identity.account"
        assert row["aggregate_id"] == account.id
        assert row["payload"] == {"display_name": "Erika"}
        assert row["status"] == "pending"
        assert row["attempts"] == 0

    async def test_leaving_without_commit_rolls_back_state_and_events(
        self, uow_factory: UnitOfWorkFactory, engine: AsyncEngine
    ) -> None:
        account, registered = Account.register_customer(
            email="kunde@example.com", display_name="Erika", password_hash="hash", now=NOW
        )
        async with uow_factory() as uow:
            uow.accounts.add(account)
            uow.publish(registered)
            await uow.flush()

        assert await outbox_rows(engine) == []
        async with uow_factory() as uow:
            assert await uow.accounts.get(account.id) is None

    async def test_failing_block_rolls_back(
        self, uow_factory: UnitOfWorkFactory, engine: AsyncEngine
    ) -> None:
        account, registered = Account.register_customer(
            email="kunde@example.com", display_name="Erika", password_hash="hash", now=NOW
        )

        async def fail_halfway() -> None:
            async with uow_factory() as uow:
                uow.accounts.add(account)
                uow.publish(registered)
                raise RuntimeError("boom")

        with pytest.raises(RuntimeError, match="boom"):
            await fail_halfway()
        assert await outbox_rows(engine) == []

    async def test_commit_notifies_the_worker(
        self, uow_factory: UnitOfWorkFactory, settings: Settings
    ) -> None:
        received: list[str] = []
        listener = await asyncpg.connect(asyncpg_dsn(settings.database_url))
        try:
            await listener.add_listener(
                "mb_outbox", lambda _c, _p, channel, _payload: received.append(channel)
            )
            account, registered = Account.register_customer(
                email="kunde@example.com", display_name="Erika", password_hash="h", now=NOW
            )
            async with uow_factory() as uow:
                uow.accounts.add(account)
                uow.publish(registered)
                await uow.commit()

            async def notified() -> list[str] | None:
                return received or None

            assert await eventually(notified) == ["mb_outbox"]
        finally:
            await listener.close()

    async def test_rejects_unregistered_events(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        async with UnitOfWork(session_factory, events=EventRegistry()) as uow:
            with pytest.raises(TypeError, match="not registered"):
                uow.publish(sample())

    async def test_custom_registry_accepts_its_events(
        self, session_factory: async_sessionmaker[AsyncSession], engine: AsyncEngine
    ) -> None:
        registry = EventRegistry()
        registry.register(SampleHappened)
        async with UnitOfWork(session_factory, events=registry) as uow:
            uow.publish(sample())
            await uow.commit()
        (row,) = await outbox_rows(engine)
        assert row["event_type"] == "test.sample.happened"

    async def test_cannot_be_entered_twice_or_used_outside(
        self, uow_factory: UnitOfWorkFactory
    ) -> None:
        uow = uow_factory()
        assert isinstance(uow, SqlIdentityUnitOfWork)
        with pytest.raises(RuntimeError, match="not active"):
            _ = uow.session
        async with uow:
            with pytest.raises(RuntimeError, match="entered twice"):
                await uow.__aenter__()

    async def test_unique_violation_is_reported_with_its_constraint(
        self, uow_factory: UnitOfWorkFactory
    ) -> None:
        async with uow_factory() as uow:
            uow.accounts.add(new_customer())
            await uow.commit()
        async with uow_factory() as uow:
            uow.accounts.add(new_customer("KUNDE@example.com"))
            with pytest.raises(UniqueViolationError) as caught:
                await uow.commit()
        assert caught.value.constraint == "uq_accounts_kind_email"

    async def test_concurrent_update_is_detected(self, uow_factory: UnitOfWorkFactory) -> None:
        account = new_customer()
        async with uow_factory() as uow:
            uow.accounts.add(account)
            await uow.commit()

        async with uow_factory() as first, uow_factory() as second:
            mine = await first.accounts.get(account.id)
            theirs = await second.accounts.get(account.id)
            assert mine is not None
            assert theirs is not None
            theirs.rename("Andere", NOW)
            await second.commit()
            mine.rename("Meine", NOW)
            with pytest.raises(ConcurrentUpdateError):
                await first.commit()

    async def test_explicit_rollback_discards_pending_events(
        self, session_factory: async_sessionmaker[AsyncSession], engine: AsyncEngine
    ) -> None:
        account, registered = Account.register_customer(
            email="kunde@example.com", display_name="Erika", password_hash="hash", now=NOW
        )
        async with SqlIdentityUnitOfWork(session_factory) as uow:
            uow.accounts.add(account)
            uow.publish(registered)
            await uow.rollback()
            await uow.commit()
        assert await outbox_rows(engine) == []


class TestRepositories:
    async def test_email_lookup_ignores_case_and_respects_kind(
        self, uow_factory: UnitOfWorkFactory
    ) -> None:
        customer = new_customer("Kunde@Example.com")
        staff = Account.create_staff(
            email="kunde@example.com",
            display_name="Doppelt",
            role=StaffRole.STAFF,
            password_hash="hash",
            now=NOW,
        )
        async with uow_factory() as uow:
            uow.accounts.add(customer)
            uow.accounts.add(staff)
            await uow.commit()

        async with uow_factory() as uow:
            found = await uow.accounts.get_by_email(AccountKind.CUSTOMER, "KUNDE@EXAMPLE.COM")
            assert found is not None
            assert found.id == customer.id
            found_staff = await uow.accounts.get_by_email(
                AccountKind.STAFF, "kunde@example.com", for_update=True
            )
            assert found_staff is not None
            assert found_staff.role is StaffRole.STAFF
            assert await uow.accounts.get_by_email(AccountKind.CUSTOMER, "x@example.com") is None

    async def test_sessions(self, uow_factory: UnitOfWorkFactory) -> None:
        account = new_customer()
        sessions = [
            LoginSession.start(
                account=account, token_hash=hash_token(str(i)), now=NOW, user_agent="Test"
            )
            for i in range(3)
        ]
        old = LoginSession.start(
            account=account,
            token_hash=hash_token("old"),
            now=NOW - timedelta(days=31),
            user_agent=None,
        )
        async with uow_factory() as uow:
            uow.accounts.add(account)
            await uow.flush()
            for session in [*sessions, old]:
                uow.sessions.add(session)
            await uow.commit()

        async with uow_factory() as uow:
            await uow.sessions.delete_expired_for_account(account.id, NOW)
            assert await uow.sessions.get(old.token_hash) is None
            await uow.sessions.delete_for_account(
                account.id, except_token_hash=sessions[0].token_hash
            )
            await uow.commit()
        async with uow_factory() as uow:
            assert await uow.sessions.get(sessions[0].token_hash) is not None
            assert await uow.sessions.get(sessions[1].token_hash) is None
            await uow.sessions.delete(sessions[0].token_hash)
            await uow.commit()
        async with uow_factory() as uow:
            assert await uow.sessions.get(sessions[0].token_hash) is None

    async def test_tokens(self, uow_factory: UnitOfWorkFactory) -> None:
        account = new_customer()
        event_id = uuid4()

        def issue(raw: str, purpose: TokenPurpose, source: object = None) -> AccountToken:
            return AccountToken.issue(
                token_hash=hash_token(raw),
                account_id=account.id,
                purpose=purpose,
                now=NOW,
                source_event_id=event_id if source else None,
            )

        used = issue("used", TokenPurpose.VERIFY_EMAIL)
        used.redeem(TokenPurpose.VERIFY_EMAIL, NOW)
        unused = issue("unused", TokenPurpose.VERIFY_EMAIL, source=True)
        reset = issue("reset", TokenPurpose.RESET_PASSWORD)
        async with uow_factory() as uow:
            uow.accounts.add(account)
            await uow.flush()
            for token in (used, unused, reset):
                uow.tokens.add(token)
            await uow.commit()

        async with uow_factory() as uow:
            assert await uow.tokens.exists_for_source_event(event_id)
            assert not await uow.tokens.exists_for_source_event(uuid4())
            await uow.tokens.delete_unused(account.id, TokenPurpose.VERIFY_EMAIL)
            await uow.commit()
        async with uow_factory() as uow:
            assert await uow.tokens.get(used.token_hash) is not None
            assert await uow.tokens.get(unused.token_hash, for_update=True) is None
            assert await uow.tokens.get(reset.token_hash) is not None
            await uow.tokens.delete_for_account(account.id)
            await uow.commit()
        async with uow_factory() as uow:
            assert await uow.tokens.get(reset.token_hash) is None


class TestConstraints:
    """The database is the last line of defence (docs/KONZEPT.md §1)."""

    async def _insert_account(self, engine: AsyncEngine, kind: str, role: str | None) -> None:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "INSERT INTO identity.accounts (id, kind, email, display_name, password_hash, "
                    "role, created_at, updated_at) VALUES (:id, :kind, :email, 'X', 'h', :role, "
                    "now(), now())"
                ),
                {"id": uuid4(), "kind": kind, "email": f"{uuid4()}@example.com", "role": role},
            )

    @pytest.mark.parametrize(("kind", "role"), [("staff", None), ("customer", "owner")])
    async def test_role_exactly_for_staff(
        self, engine: AsyncEngine, kind: str, role: str | None
    ) -> None:
        with pytest.raises(IntegrityError, match="ck_accounts_role_only_for_staff"):
            await self._insert_account(engine, kind, role)

    async def test_session_kind_must_match_account_kind(
        self, uow_factory: UnitOfWorkFactory, engine: AsyncEngine
    ) -> None:
        account = new_customer()
        async with uow_factory() as uow:
            uow.accounts.add(account)
            await uow.commit()
        with pytest.raises(IntegrityError, match="fk_sessions_account_id_kind_accounts"):
            async with engine.begin() as connection:
                await connection.execute(
                    text(
                        "INSERT INTO identity.sessions (token_hash, account_id, kind, created_at, "
                        "expires_at, last_seen_at) VALUES (:hash, :id, 'staff', now(), "
                        "now() + interval '1 hour', now())"
                    ),
                    {"hash": hash_token("x"), "id": account.id},
                )

    async def test_published_events_need_a_timestamp(self, engine: AsyncEngine) -> None:
        with pytest.raises(IntegrityError, match="ck_outbox_published_at"):
            async with engine.begin() as connection:
                await connection.execute(
                    text(
                        "INSERT INTO platform.outbox (id, event_type, aggregate_type, "
                        "aggregate_id, payload, occurred_at, status) VALUES (:id, 't', 'a', "
                        ":id, '{}', now(), 'published')"
                    ),
                    {"id": uuid4()},
                )

    async def test_token_hashes_must_be_sha256_hex(self, uow_factory: UnitOfWorkFactory) -> None:
        account = new_customer()
        async with uow_factory() as uow:
            uow.accounts.add(account)
            await uow.flush()
            uow.tokens.add(
                AccountToken.issue(
                    token_hash="raw-token-not-hashed".ljust(64, "x"),
                    account_id=account.id,
                    purpose=TokenPurpose.VERIFY_EMAIL,
                    now=NOW,
                    source_event_id=None,
                )
            )
            with pytest.raises(IntegrityError, match="ck_account_tokens_token_hash_format"):
                await uow.commit()


class TestContracts:
    async def test_account_summary(self, uow_factory: UnitOfWorkFactory) -> None:
        account = new_customer()
        account.verify_email(NOW)
        async with uow_factory() as uow:
            uow.accounts.add(account)
            await uow.commit()

        async with uow_factory() as uow:
            assert isinstance(uow, UnitOfWork)
            summary = await get_account_summary(uow, account.id)
            assert await get_account_summary(uow, uuid4()) is None
        assert summary is not None
        assert summary.kind is AccountKind.CUSTOMER
        assert summary.email == "kunde@example.com"
        assert summary.email_verified
        assert summary.active
        assert summary.role is None
