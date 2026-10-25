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

from modellbahn.modules.catalog.application.scales import ScaleService
from modellbahn.modules.catalog.application.services import CatalogService
from modellbahn.modules.catalog.application.services import (
    UnitOfWorkFactory as CatalogUnitOfWorkFactory,
)
from modellbahn.modules.catalog.infrastructure.repositories import catalog_uow_factory
from modellbahn.modules.identity.application.handlers import IdentityMailHandlers
from modellbahn.modules.identity.application.services import IdentityService, UnitOfWorkFactory
from modellbahn.modules.identity.infrastructure.mapping import start_mappers
from modellbahn.modules.identity.infrastructure.repositories import SqlIdentityUnitOfWork
from modellbahn.modules.media.application.handlers import MediaProcessingHandlers
from modellbahn.modules.media.application.services import MediaService
from modellbahn.modules.media.application.services import (
    UnitOfWorkFactory as MediaUnitOfWorkFactory,
)
from modellbahn.modules.media.infrastructure.imaging import PillowImageProcessor
from modellbahn.modules.media.infrastructure.repositories import SqlMediaUnitOfWork
from modellbahn.modules.sales.application.addresses import AddressService
from modellbahn.modules.sales.application.cart import CartService
from modellbahn.modules.sales.application.checkout import CheckoutService
from modellbahn.modules.sales.application.common import (
    UnitOfWorkFactory as SalesUnitOfWorkFactory,
)
from modellbahn.modules.sales.application.handlers import SalesHandlers
from modellbahn.modules.sales.application.orders import OrderService
from modellbahn.modules.sales.infrastructure.payments import MockPaymentGateway
from modellbahn.modules.sales.infrastructure.repositories import sales_uow_factory
from modellbahn.platform.clock import FixedClock
from modellbahn.platform.config import Environment, Settings
from modellbahn.platform.db import asyncpg_dsn, create_engine, create_session_factory
from modellbahn.platform.events import event_registry
from modellbahn.platform.mail import InMemoryMailer
from modellbahn.platform.outbox import HandlerRegistry, OutboxDispatcher
from modellbahn.platform.security import Argon2PasswordHasher
from tests.media_support import InMemoryMediaStorage
from tests.support import create_database, drop_database, migrate

DEFAULT_POSTGRES_IMAGE = "postgres:17-alpine"
PUBLIC_BASE_URL = "https://shop.test"
SHOP_NAME = "Modellbahn-Shop"
MEDIA_BASE_URL = "/medien"


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
        # Tests log in and register far more often than a person; test_rate_limit
        # switches the limit on for itself.
        auth_rate_limit=0,
        media_public_base_url=MEDIA_BASE_URL,
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


# Every table a test can write to. The catalogue's finishes and epochs come from the
# migration and stay; scales are reset to the migration's set (tests may change them).
WRITABLE_TABLES = (
    "platform.outbox",
    "inventory.stock_ledger",
    "inventory.scans",
    "inventory.units",
    "inventory.allocations",
    "inventory.locations",
    "sales.cart_lines",
    "sales.carts",
    "sales.payments",
    "sales.order_lines",
    "sales.orders",
    "sales.customer_addresses",
    "catalog.product_media",
    "catalog.variants",
    "catalog.product_scales",
    "catalog.product_epochs",
    "catalog.products",
    "catalog.categories",
    "media.renditions",
    "media.image_details",
    "media.assets",
    "identity.account_tokens",
    "identity.sessions",
    "identity.accounts",
)


# The scales migrations 0002 and 0004 create.
RESET_SCALES = """
INSERT INTO catalog.scales (code, name, ratio_denominator, track_gauge_mm) VALUES
    ('Z', 'Z', 220, 6.5), ('N', 'N', 160, 9.0), ('TT', 'TT', 120, 12.0),
    ('H0', 'H0', 87, 16.5), ('0', '0', 45, 32.0), ('125', '1:25', 25, NULL),
    ('124', '1:24', 24, NULL), ('G', 'G', 22.5, 45.0)
"""


@pytest.fixture
async def clean_database(engine: AsyncEngine) -> None:
    """Empty every table, so that each test starts from scratch."""
    async with engine.begin() as connection:
        await connection.execute(text(f"TRUNCATE {', '.join(WRITABLE_TABLES)}"))
        await connection.execute(text("DELETE FROM catalog.scales"))
        await connection.execute(text(RESET_SCALES))


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


@pytest.fixture
def media_storage() -> InMemoryMediaStorage:
    return InMemoryMediaStorage()


@pytest.fixture
def media_uow_factory(session_factory: async_sessionmaker[AsyncSession]) -> MediaUnitOfWorkFactory:
    return partial(SqlMediaUnitOfWork, session_factory)


@pytest.fixture
def media(
    media_uow_factory: MediaUnitOfWorkFactory,
    media_storage: InMemoryMediaStorage,
    clock: FixedClock,
) -> MediaService:
    return MediaService(uow_factory=media_uow_factory, storage=media_storage, clock=clock)


@pytest.fixture(scope="session")
def image_processor() -> PillowImageProcessor:
    return PillowImageProcessor()


@pytest.fixture
def media_handlers(
    media_uow_factory: MediaUnitOfWorkFactory,
    media_storage: InMemoryMediaStorage,
    image_processor: PillowImageProcessor,
    clock: FixedClock,
) -> MediaProcessingHandlers:
    return MediaProcessingHandlers(
        uow_factory=media_uow_factory, storage=media_storage, processor=image_processor, clock=clock
    )


@pytest.fixture
def catalog_uow(session_factory: async_sessionmaker[AsyncSession]) -> CatalogUnitOfWorkFactory:
    return catalog_uow_factory(session_factory, public_base_url=MEDIA_BASE_URL)


@pytest.fixture
def catalog(catalog_uow: CatalogUnitOfWorkFactory, clock: FixedClock) -> CatalogService:
    return CatalogService(uow_factory=catalog_uow, clock=clock)


@pytest.fixture
def scale_service(catalog_uow: CatalogUnitOfWorkFactory) -> ScaleService:
    return ScaleService(uow_factory=catalog_uow)


@pytest.fixture
def sales_uow(session_factory: async_sessionmaker[AsyncSession]) -> SalesUnitOfWorkFactory:
    return sales_uow_factory(session_factory, public_base_url=MEDIA_BASE_URL)


@pytest.fixture
def payment_gateway() -> MockPaymentGateway:
    return MockPaymentGateway()


@pytest.fixture
def carts(sales_uow: SalesUnitOfWorkFactory, clock: FixedClock) -> CartService:
    return CartService(uow_factory=sales_uow, clock=clock)


@pytest.fixture
def checkout(
    sales_uow: SalesUnitOfWorkFactory, clock: FixedClock, payment_gateway: MockPaymentGateway
) -> CheckoutService:
    return CheckoutService(uow_factory=sales_uow, clock=clock, gateway=payment_gateway)


@pytest.fixture
def orders(
    sales_uow: SalesUnitOfWorkFactory, clock: FixedClock, payment_gateway: MockPaymentGateway
) -> OrderService:
    return OrderService(uow_factory=sales_uow, clock=clock, gateway=payment_gateway)


@pytest.fixture
def addresses(sales_uow: SalesUnitOfWorkFactory, clock: FixedClock) -> AddressService:
    return AddressService(uow_factory=sales_uow, clock=clock)


@pytest.fixture
def sales_handlers(
    sales_uow: SalesUnitOfWorkFactory, mailer: InMemoryMailer, clock: FixedClock
) -> SalesHandlers:
    return SalesHandlers(
        uow_factory=sales_uow,
        mailer=mailer,
        clock=clock,
        public_base_url=PUBLIC_BASE_URL,
        shop_name=SHOP_NAME,
    )


type Deliver = Callable[[], Awaitable[int]]


@pytest.fixture
def deliver(
    engine: AsyncEngine,
    settings: Settings,
    mail_handlers: IdentityMailHandlers,
    media_handlers: MediaProcessingHandlers,
    sales_handlers: SalesHandlers,
) -> Deliver:
    """Run one batch of the real outbox dispatcher with the handlers of all modules."""
    handlers = HandlerRegistry()
    mail_handlers.register(handlers)
    media_handlers.register(handlers)
    sales_handlers.register(handlers)
    dispatcher = OutboxDispatcher(
        engine=engine,
        listen_dsn=asyncpg_dsn(settings.database_url),
        events=event_registry,
        handlers=handlers,
        poll_seconds=settings.outbox_poll_seconds,
        max_attempts=settings.outbox_max_attempts,
    )
    return dispatcher.dispatch_batch
