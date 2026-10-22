"""Fixtures shared by all tests.

Integration and API tests run against a real PostgreSQL: ``TEST_DATABASE_URL`` if set
(CI uses a service container), otherwise a throwaway container started through
testcontainers with ``TEST_POSTGRES_IMAGE`` (default ``postgres:17-alpine``). Each test
session creates a fresh database on that server and migrates it once.
"""

import asyncio
import os
import secrets
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from datetime import UTC, datetime
from functools import partial

import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from modellbahn.modules.identity.application.handlers import IdentityMailHandlers
from modellbahn.modules.identity.application.services import IdentityService, UnitOfWorkFactory
from modellbahn.modules.identity.infrastructure.mapping import start_mappers
from modellbahn.modules.identity.infrastructure.repositories import SqlIdentityUnitOfWork
from modellbahn.platform.clock import FixedClock
from modellbahn.platform.config import Environment, Settings
from modellbahn.platform.db import asyncpg_dsn, create_engine, create_session_factory
from modellbahn.platform.events import event_registry
from modellbahn.platform.mail import InMemoryMailer
from modellbahn.platform.outbox import HandlerRegistry, OutboxDispatcher
from modellbahn.platform.security import Argon2PasswordHasher
from tests.support import create_database, drop_database, migrate

DEFAULT_POSTGRES_IMAGE = "postgres:17-alpine"
PUBLIC_BASE_URL = "https://shop.test"
SHOP_NAME = "Modellbahn-Shop"


@pytest.fixture(scope="session")
def postgres_server_url() -> Iterator[str]:
    """URL of a PostgreSQL server whose user may create databases."""
    configured = os.environ.get("TEST_DATABASE_URL")
    # testcontainers (and the Docker SDK) are only imported when no server is configured.
    if configured:
        yield (
            make_url(configured)
            .set(drivername="postgresql+asyncpg")
            .render_as_string(hide_password=False)
        )
        return
    from testcontainers.community.postgres import PostgresContainer  # noqa: PLC0415

    image = os.environ.get("TEST_POSTGRES_IMAGE", DEFAULT_POSTGRES_IMAGE)
    with PostgresContainer(image, driver="asyncpg") as container:
        yield container.get_connection_url()


@pytest.fixture(scope="session")
def database_url(postgres_server_url: str) -> Iterator[str]:
    """A fresh, migrated database for this test session."""
    name = f"modellbahn_test_{secrets.token_hex(6)}"
    url = asyncio.run(create_database(postgres_server_url, name))
    try:
        migrate(url)
        yield url
    finally:
        asyncio.run(drop_database(postgres_server_url, name))


@pytest.fixture(scope="session")
def settings(database_url: str) -> Settings:
    return Settings(
        database_url=database_url,
        environment=Environment.TEST,
        public_base_url=PUBLIC_BASE_URL,
        cookie_secure=True,
        smtp_from=f"{SHOP_NAME} <noreply@modellbahn.local>",
        # Fast hashing for tests; production uses the library defaults.
        argon2_time_cost=1,
        argon2_memory_cost=8,
        argon2_parallelism=1,
        outbox_poll_seconds=0.2,
        outbox_max_attempts=3,
        log_level="WARNING",
    )


@pytest.fixture(scope="session")
async def engine(settings: Settings) -> AsyncIterator[AsyncEngine]:
    start_mappers()
    engine = create_engine(settings.database_url)
    yield engine
    await engine.dispose()


@pytest.fixture(scope="session")
def session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return create_session_factory(engine)


@pytest.fixture
async def clean_database(engine: AsyncEngine) -> None:
    """Empty every table, so that each test starts from scratch."""
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "TRUNCATE platform.outbox, identity.account_tokens, identity.sessions, "
                "identity.accounts"
            )
        )


@pytest.fixture
def uow_factory(session_factory: async_sessionmaker[AsyncSession]) -> UnitOfWorkFactory:
    return partial(SqlIdentityUnitOfWork, session_factory)


@pytest.fixture(scope="session")
def hasher(settings: Settings) -> Argon2PasswordHasher:
    return Argon2PasswordHasher.from_settings(settings)


@pytest.fixture
def clock() -> FixedClock:
    return FixedClock(datetime(2026, 10, 22, 10, 0, tzinfo=UTC))


@pytest.fixture
def mailer() -> InMemoryMailer:
    return InMemoryMailer()


@pytest.fixture
def identity(
    uow_factory: UnitOfWorkFactory, hasher: Argon2PasswordHasher, clock: FixedClock
) -> IdentityService:
    return IdentityService(uow_factory=uow_factory, hasher=hasher, clock=clock)


@pytest.fixture
def mail_handlers(
    uow_factory: UnitOfWorkFactory, mailer: InMemoryMailer, clock: FixedClock
) -> IdentityMailHandlers:
    return IdentityMailHandlers(
        uow_factory=uow_factory,
        mailer=mailer,
        clock=clock,
        public_base_url=PUBLIC_BASE_URL,
        shop_name=SHOP_NAME,
    )


type Deliver = Callable[[], Awaitable[int]]


@pytest.fixture
def deliver(
    engine: AsyncEngine, settings: Settings, mail_handlers: IdentityMailHandlers
) -> Deliver:
    """Run one batch of the real outbox dispatcher with the identity handlers."""
    handlers = HandlerRegistry()
    mail_handlers.register(handlers)
    dispatcher = OutboxDispatcher(
        engine=engine,
        listen_dsn=asyncpg_dsn(settings.database_url),
        events=event_registry,
        handlers=handlers,
        poll_seconds=settings.outbox_poll_seconds,
        max_attempts=settings.outbox_max_attempts,
    )
    return dispatcher.dispatch_batch
