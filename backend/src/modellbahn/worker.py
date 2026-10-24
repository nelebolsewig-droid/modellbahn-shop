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
from modellbahn.modules.media.application.handlers import MediaProcessingHandlers
from modellbahn.modules.media.application.ports import ImageProcessor, MediaStorage
from modellbahn.modules.media.application.services import MediaService
from modellbahn.modules.media.infrastructure.imaging import PillowImageProcessor
from modellbahn.modules.media.infrastructure.mapping import start_mappers as start_media_mappers
from modellbahn.modules.media.infrastructure.repositories import SqlMediaUnitOfWork
from modellbahn.modules.media.infrastructure.storage import S3MediaStorage
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
FORWARDED_EVENT_MODULES: Final = (catalog_events,)


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
    clock = SystemClock()
    storage = media_storage or S3MediaStorage.from_settings(settings)
    media_uow = partial(SqlMediaUnitOfWork, session_factory)

    handlers = HandlerRegistry()
    IdentityMailHandlers(
        uow_factory=partial(SqlIdentityUnitOfWork, session_factory),
        mailer=mailer or SmtpMailer(settings),
        clock=clock,
        public_base_url=settings.public_base_url,
        shop_name=settings.shop_name,
    ).register(handlers)
    MediaProcessingHandlers(
        uow_factory=media_uow,
        storage=storage,
        processor=image_processor or PillowImageProcessor(),
        clock=clock,
    ).register(handlers)
    media_service = MediaService(uow_factory=media_uow, storage=storage, clock=clock)
    jobs = [
        PeriodicJob(
            name="media.purge_stale_uploads",
            interval=STALE_UPLOAD_SWEEP_INTERVAL,
            run=media_service.purge_stale_uploads,
        )
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
