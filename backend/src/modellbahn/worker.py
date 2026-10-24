"""The worker process: ``python -m modellbahn.worker`` dispatches the outbox until SIGTERM."""

import asyncio
import signal
from functools import partial

import structlog

from modellbahn.modules.identity.application.handlers import IdentityMailHandlers
from modellbahn.modules.identity.infrastructure.mapping import start_mappers
from modellbahn.modules.identity.infrastructure.repositories import SqlIdentityUnitOfWork
from modellbahn.platform.clock import SystemClock
from modellbahn.platform.config import Settings
from modellbahn.platform.db import asyncpg_dsn, create_engine, create_session_factory
from modellbahn.platform.events import event_registry
from modellbahn.platform.logging import configure_logging
from modellbahn.platform.mail import Mailer, SmtpMailer
from modellbahn.platform.outbox import HandlerRegistry, OutboxDispatcher

# Named explicitly: under "python -m" this module is called __main__.
_logger = structlog.get_logger("modellbahn.worker")


async def run_worker(
    settings: Settings, stop: asyncio.Event, *, mailer: Mailer | None = None
) -> None:
    """Wire the handlers of all modules and dispatch until ``stop`` is set."""
    engine = create_engine(settings.database_url)
    session_factory = create_session_factory(engine)
    start_mappers()

    handlers = HandlerRegistry()
    IdentityMailHandlers(
        uow_factory=partial(SqlIdentityUnitOfWork, session_factory),
        mailer=mailer or SmtpMailer(settings),
        clock=SystemClock(),
        public_base_url=settings.public_base_url,
        shop_name=settings.shop_name,
    ).register(handlers)

    dispatcher = OutboxDispatcher(
        engine=engine,
        listen_dsn=asyncpg_dsn(settings.database_url),
        events=event_registry,
        handlers=handlers,
        poll_seconds=settings.outbox_poll_seconds,
        max_attempts=settings.outbox_max_attempts,
    )
    try:
        await dispatcher.run(stop)
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
