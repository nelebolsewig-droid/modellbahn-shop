"""The worker process: ``python -m modellbahn.worker`` dispatches the outbox until SIGTERM."""

import asyncio
import signal
from datetime import timedelta
from functools import partial
from typing import Final

import structlog

# Modules whose events the worker only forwards (no handler here) are imported for their
# event classes: the dispatcher must deserialize every event type in the outbox.
from modellbahn.modules.catalog.contracts import events as catalog_events
from modellbahn.modules.identity.application.handlers import IdentityMailHandlers
from modellbahn.modules.identity.infrastructure.mapping import (
    start_mappers as start_identity_mappers,
)
from modellbahn.modules.identity.infrastructure.repositories import SqlIdentityUnitOfWork
from modellbahn.modules.inventory.application.allocation import AllocationService
from modellbahn.modules.inventory.application.handlers import InventoryHandlers
from modellbahn.modules.inventory.application.parts import PartStoreService
from modellbahn.modules.inventory.infrastructure.repositories import inventory_uow_factory
from modellbahn.modules.manufacturing.contracts import events as manufacturing_events
from modellbahn.modules.marketplace.application.handlers import MarketplaceHandlers
from modellbahn.modules.marketplace.contracts import events as marketplace_events
from modellbahn.modules.marketplace.infrastructure.setup import build_marketplace
from modellbahn.modules.media.application.handlers import MediaProcessingHandlers
from modellbahn.modules.media.application.ports import ImageProcessor, MediaStorage
from modellbahn.modules.media.application.services import MediaService
from modellbahn.modules.media.infrastructure.imaging import PillowImageProcessor
from modellbahn.modules.media.infrastructure.mapping import start_mappers as start_media_mappers
from modellbahn.modules.media.infrastructure.repositories import SqlMediaUnitOfWork
from modellbahn.modules.media.infrastructure.storage import S3MediaStorage
from modellbahn.modules.sales.application.cart import CartService
from modellbahn.modules.sales.application.handlers import SalesHandlers
from modellbahn.modules.sales.application.marketplace import MarketplaceIntake
from modellbahn.modules.sales.application.orders import OrderService
from modellbahn.modules.sales.infrastructure.payments import MockPaymentGateway
from modellbahn.modules.sales.infrastructure.repositories import sales_uow_factory
from modellbahn.modules.site.application.handlers import SiteHandlers
from modellbahn.modules.site.application.subscriptions import SubscriptionService
from modellbahn.modules.site.infrastructure.mapping import start_mappers as start_site_mappers
from modellbahn.modules.site.infrastructure.repositories import site_uow_factory
from modellbahn.platform.clock import SystemClock
from modellbahn.platform.config import Settings
from modellbahn.platform.db import asyncpg_dsn, create_engine, create_session_factory
from modellbahn.platform.events import event_registry
from modellbahn.platform.logging import configure_logging
from modellbahn.platform.mail import Mailer, SmtpMailer
from modellbahn.platform.outbox import HandlerRegistry, OutboxDispatcher
from modellbahn.platform.periodic import PeriodicJob, run_periodically

# Named explicitly: under "python -m" this module is called __main__.
_logger = structlog.get_logger("modellbahn.worker")

STALE_UPLOAD_SWEEP_INTERVAL: Final = timedelta(hours=1)
OVERDUE_ORDER_SWEEP_INTERVAL: Final = timedelta(minutes=15)
EXPIRED_CART_SWEEP_INTERVAL: Final = timedelta(hours=6)
PENDING_SUBSCRIPTION_SWEEP_INTERVAL: Final = timedelta(hours=6)
EBAY_LISTING_SYNC_INTERVAL: Final = timedelta(minutes=1)
EBAY_ORDER_FETCH_INTERVAL: Final = timedelta(minutes=2)
# The marketplace's events stay readable with MB_EBAY_MODE=off (the setting may change).
FORWARDED_EVENT_MODULES: Final = (catalog_events, marketplace_events, manufacturing_events)


async def run_worker(
    settings: Settings,
    stop: asyncio.Event,
    *,
    mailer: Mailer | None = None,
    media_storage: MediaStorage | None = None,
    image_processor: ImageProcessor | None = None,
) -> None:
    """Wire the handlers and jobs of all modules and run them until ``stop`` is set."""
    engine = create_engine(settings.database_url)
    session_factory = create_session_factory(engine)
    start_identity_mappers()
    start_media_mappers()
    start_site_mappers()
    clock = SystemClock()
    storage = media_storage or S3MediaStorage.from_settings(settings)
    media_uow = partial(SqlMediaUnitOfWork, session_factory)
    sales_uow = sales_uow_factory(session_factory, public_base_url=settings.media_public_base_url)
    mailer = mailer or SmtpMailer(settings)

    handlers = HandlerRegistry()
    IdentityMailHandlers(
        uow_factory=partial(SqlIdentityUnitOfWork, session_factory),
        mailer=mailer,
        clock=clock,
        public_base_url=settings.public_base_url,
        shop_name=settings.shop_name,
        sender=settings.imprint.mail_footer(),
    ).register(handlers)
    SalesHandlers(
        uow_factory=sales_uow,
        mailer=mailer,
        clock=clock,
        public_base_url=settings.public_base_url,
        shop_name=settings.shop_name,
        sender=settings.imprint.mail_footer(),
    ).register(handlers)
    site_uow = site_uow_factory(session_factory)
    SiteHandlers(
        uow_factory=site_uow,
        mailer=mailer,
        clock=clock,
        public_base_url=settings.public_base_url,
        shop_name=settings.shop_name,
        sender=settings.imprint.mail_footer(),
    ).register(handlers)
    MarketplaceIntake(uow_factory=sales_uow, clock=clock).register(handlers)
    marketplace = build_marketplace(settings, session_factory, clock)
    if marketplace is not None:
        MarketplaceHandlers(
            uow_factory=marketplace.uow_factory, orders=marketplace.orders, clock=clock
        ).register(handlers)
    inventory_uow = inventory_uow_factory(session_factory)
    InventoryHandlers(
        allocation=AllocationService(uow_factory=inventory_uow, clock=clock),
        parts=PartStoreService(uow_factory=inventory_uow, clock=clock),
    ).register(handlers)
    MediaProcessingHandlers(
        uow_factory=media_uow,
        storage=storage,
        processor=image_processor or PillowImageProcessor(),
        clock=clock,
    ).register(handlers)
    media_service = MediaService(uow_factory=media_uow, storage=storage, clock=clock)
    order_service = OrderService(uow_factory=sales_uow, clock=clock, gateway=MockPaymentGateway())
    cart_service = CartService(uow_factory=sales_uow, clock=clock)
    jobs = [
        PeriodicJob(
            name="media.purge_stale_uploads",
            interval=STALE_UPLOAD_SWEEP_INTERVAL,
            run=media_service.purge_stale_uploads,
        ),
        PeriodicJob(
            name="sales.cancel_overdue_orders",
            interval=OVERDUE_ORDER_SWEEP_INTERVAL,
            run=order_service.cancel_overdue,
        ),
        PeriodicJob(
            name="sales.purge_expired_carts",
            interval=EXPIRED_CART_SWEEP_INTERVAL,
            run=cart_service.purge_expired,
        ),
        PeriodicJob(
            name="site.purge_pending_subscriptions",
            interval=PENDING_SUBSCRIPTION_SWEEP_INTERVAL,
            run=SubscriptionService(uow_factory=site_uow, clock=clock).purge_pending,
        ),
    ]
    if marketplace is not None:
        jobs += [
            PeriodicJob(
                name="marketplace.sync_listings",
                interval=EBAY_LISTING_SYNC_INTERVAL,
                run=marketplace.listings.sync_due,
            ),
            PeriodicJob(
                name="marketplace.fetch_orders",
                interval=EBAY_ORDER_FETCH_INTERVAL,
                run=marketplace.orders.fetch,
            ),
        ]

    dispatcher = OutboxDispatcher(
        engine=engine,
        listen_dsn=asyncpg_dsn(settings.database_url),
        events=event_registry,
        handlers=handlers,
        poll_seconds=settings.outbox_poll_seconds,
        max_attempts=settings.outbox_max_attempts,
    )
    try:
        async with asyncio.TaskGroup() as group:
            group.create_task(dispatcher.run(stop))
            for job in jobs:
                group.create_task(run_periodically(job, stop))
    finally:
        if marketplace is not None:
            await marketplace.aclose()
        await engine.dispose()


async def _serve(settings: Settings) -> None:
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for signum in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(signum, _request_stop, stop, signum)
    await run_worker(settings, stop)


def _request_stop(stop: asyncio.Event, signum: int) -> None:
    _logger.info("worker.stopping", signal=signal.Signals(signum).name)
    stop.set()


def main() -> None:
    settings = Settings()
    configure_logging(environment=settings.environment, level=settings.log_level)
    asyncio.run(_serve(settings))


if __name__ == "__main__":
    main()
