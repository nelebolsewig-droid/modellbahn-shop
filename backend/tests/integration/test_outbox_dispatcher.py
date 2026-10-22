"""The outbox dispatcher against a real PostgreSQL."""

import asyncio
import json
from collections.abc import Awaitable, Callable
from datetime import timedelta
from uuid import UUID, uuid4

import asyncpg
import pytest
from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from modellbahn.modules.identity.application.services import UnitOfWorkFactory
from modellbahn.modules.identity.domain.model import Account
from modellbahn.platform.config import Settings
from modellbahn.platform.db import asyncpg_dsn, create_engine
from modellbahn.platform.events import EventRegistry, event_registry
from modellbahn.platform.outbox import HandlerRegistry, OutboxDispatcher, outbox_table
from modellbahn.platform.uow import UnitOfWork
from tests.support import NOW, SampleHappened, eventually, sample


@pytest.fixture
def events() -> EventRegistry:
    registry = EventRegistry()
    registry.register(SampleHappened)
    return registry


@pytest.fixture
def make_dispatcher(
    engine: AsyncEngine, settings: Settings, events: EventRegistry
) -> Callable[..., OutboxDispatcher]:
    def make(
        handlers: HandlerRegistry,
        *,
        max_attempts: int = 3,
        batch_size: int = 20,
        poll_seconds: float = 0.2,
        registry: EventRegistry | None = None,
    ) -> OutboxDispatcher:
        return OutboxDispatcher(
            engine=engine,
            listen_dsn=asyncpg_dsn(settings.database_url),
            events=registry or events,
            handlers=handlers,
            poll_seconds=poll_seconds,
            max_attempts=max_attempts,
            batch_size=batch_size,
        )

    return make


@pytest.fixture
def publish(
    session_factory: async_sessionmaker[AsyncSession], events: EventRegistry
) -> Callable[[int], Awaitable[list[SampleHappened]]]:
    async def publish(count: int = 1) -> list[SampleHappened]:
        published = [sample() for _ in range(count)]
        async with UnitOfWork(session_factory, events=events) as uow:
            uow.publish(*published)
            await uow.commit()
        return published

    return publish


async def row(engine: AsyncEngine, event_id: UUID) -> dict[str, object]:
    async with engine.connect() as connection:
        result = await connection.execute(
            select(outbox_table, func.now().label("db_now")).where(outbox_table.c.id == event_id)
        )
        return dict(result.one()._mapping)


async def test_successful_handling_publishes_the_event(
    make_dispatcher: Callable[..., OutboxDispatcher],
    publish: Callable[[int], Awaitable[list[SampleHappened]]],
    engine: AsyncEngine,
) -> None:
    received: list[SampleHappened] = []

    async def handler(event: SampleHappened) -> None:
        received.append(event)

    handlers = HandlerRegistry()
    handlers.register(SampleHappened, handler)
    (event,) = await publish(1)

    assert await make_dispatcher(handlers).dispatch_batch() == 1

    assert received == [event]
    stored = await row(engine, event.event_id)
    assert stored["status"] == "published"
    assert stored["published_at"] is not None
    assert stored["attempts"] == 0


async def test_events_without_handlers_are_published(
    make_dispatcher: Callable[..., OutboxDispatcher],
    publish: Callable[[int], Awaitable[list[SampleHappened]]],
    engine: AsyncEngine,
) -> None:
    (event,) = await publish(1)
    await make_dispatcher(HandlerRegistry()).dispatch_batch()
    assert (await row(engine, event.event_id))["status"] == "published"


async def test_failure_schedules_a_retry_with_backoff(
    make_dispatcher: Callable[..., OutboxDispatcher],
    publish: Callable[[int], Awaitable[list[SampleHappened]]],
    engine: AsyncEngine,
) -> None:
    async def broken(event: SampleHappened) -> None:
        raise RuntimeError("SMTP kaputt")

    handlers = HandlerRegistry()
    handlers.register(SampleHappened, broken)
    dispatcher = make_dispatcher(handlers)
    (event,) = await publish(1)

    assert await dispatcher.dispatch_batch() == 1
    stored = await row(engine, event.event_id)
    assert stored["status"] == "pending"
    assert stored["attempts"] == 1
    assert stored["last_error"] == "RuntimeError: SMTP kaputt"
    delay = stored["next_attempt_at"] - stored["db_now"]  # type: ignore[operator]
    assert timedelta(seconds=29) < delay <= timedelta(seconds=30)

    # Not due yet, so the next batch leaves it alone.
    assert await dispatcher.dispatch_batch() == 0


async def test_event_is_dead_after_max_attempts(
    make_dispatcher: Callable[..., OutboxDispatcher],
    publish: Callable[[int], Awaitable[list[SampleHappened]]],
    engine: AsyncEngine,
) -> None:
    async def broken(event: SampleHappened) -> None:
        raise RuntimeError("immer kaputt")

    handlers = HandlerRegistry()
    handlers.register(SampleHappened, broken)
    dispatcher = make_dispatcher(handlers, max_attempts=2)
    (event,) = await publish(1)

    await dispatcher.dispatch_batch()
    async with engine.begin() as connection:
        await connection.execute(
            update(outbox_table)
            .where(outbox_table.c.id == event.event_id)
            .values(next_attempt_at=func.now())
        )
    await dispatcher.dispatch_batch()

    stored = await row(engine, event.event_id)
    assert stored["status"] == "dead"
    assert stored["attempts"] == 2
    assert stored["published_at"] is None
    assert await dispatcher.dispatch_batch() == 0


async def test_unknown_event_types_fail_instead_of_vanishing(
    make_dispatcher: Callable[..., OutboxDispatcher], engine: AsyncEngine
) -> None:
    event_id = uuid4()
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "INSERT INTO platform.outbox (id, event_type, aggregate_type, aggregate_id, "
                "payload, occurred_at) VALUES (:id, 'test.unknown', 'test', :id, '{}', now())"
            ),
            {"id": event_id},
        )
    await make_dispatcher(HandlerRegistry()).dispatch_batch()
    stored = await row(engine, event_id)
    assert stored["status"] == "pending"
    assert stored["last_error"] == "UnknownEventTypeError: test.unknown"


async def test_two_concurrent_dispatchers_never_process_the_same_event(
    make_dispatcher: Callable[..., OutboxDispatcher],
    publish: Callable[[int], Awaitable[list[SampleHappened]]],
    engine: AsyncEngine,
) -> None:
    published = await publish(60)
    processed_by: dict[str, list[UUID]] = {"first": [], "second": []}

    def recording(name: str) -> HandlerRegistry:
        async def handler(event: SampleHappened) -> None:
            processed_by[name].append(event.event_id)
            # Hold the claimed rows for a moment, as a real handler would.
            await asyncio.sleep(0.005)

        handlers = HandlerRegistry()
        handlers.register(SampleHappened, handler)
        return handlers

    async def drain(dispatcher: OutboxDispatcher) -> None:
        while await dispatcher.dispatch_batch():
            pass

    first = make_dispatcher(recording("first"), batch_size=5)
    second = make_dispatcher(recording("second"), batch_size=5)
    await asyncio.gather(drain(first), drain(second))

    processed = processed_by["first"] + processed_by["second"]
    assert len(processed) == len(set(processed)) == len(published)
    assert set(processed) == {event.event_id for event in published}
    # Both really worked in parallel, otherwise the test proves nothing.
    assert processed_by["first"]
    assert processed_by["second"]
    async with engine.connect() as connection:
        statuses = await connection.scalars(select(outbox_table.c.status).distinct())
        assert set(statuses) == {"published"}


async def test_run_wakes_up_on_notify_and_stops_gracefully(
    make_dispatcher: Callable[..., OutboxDispatcher],
    publish: Callable[[int], Awaitable[list[SampleHappened]]],
) -> None:
    handled = asyncio.Event()

    async def handler(event: SampleHappened) -> None:
        handled.set()

    handlers = HandlerRegistry()
    handlers.register(SampleHappened, handler)
    # Polling alone would take a minute; only NOTIFY can make this fast.
    dispatcher = make_dispatcher(handlers, poll_seconds=60)
    stop = asyncio.Event()
    task = asyncio.create_task(dispatcher.run(stop))
    await asyncio.sleep(0.3)

    await publish(1)
    async with asyncio.timeout(5):
        await handled.wait()

    stop.set()
    async with asyncio.timeout(5):
        await task


async def test_run_survives_an_unreachable_database(settings: Settings) -> None:
    unreachable = "postgresql+asyncpg://nobody:secret@127.0.0.1:1/nothing"
    engine = create_engine(unreachable)
    dispatcher = OutboxDispatcher(
        engine=engine,
        listen_dsn=asyncpg_dsn(unreachable),
        events=EventRegistry(),
        handlers=HandlerRegistry(),
        poll_seconds=0.05,
        max_attempts=3,
    )
    stop = asyncio.Event()
    task = asyncio.create_task(dispatcher.run(stop))
    await asyncio.sleep(0.3)
    assert not task.done()
    stop.set()
    async with asyncio.timeout(5):
        await task
    await engine.dispose()


async def test_published_staff_events_are_forwarded_to_the_api(
    make_dispatcher: Callable[..., OutboxDispatcher],
    uow_factory: UnitOfWorkFactory,
    settings: Settings,
) -> None:
    notifications: list[str] = []
    listener = await asyncpg.connect(asyncpg_dsn(settings.database_url))
    await listener.add_listener(
        "mb_events", lambda _c, _p, _channel, payload: notifications.append(payload)
    )
    try:
        account, registered = Account.register_customer(
            email="kunde@example.com", display_name="Erika", password_hash="h", now=NOW
        )
        async with uow_factory() as uow:
            uow.accounts.add(account)
            uow.publish(registered)
            await uow.commit()

        await make_dispatcher(HandlerRegistry(), registry=event_registry).dispatch_batch()

        async def received() -> list[str] | None:
            return notifications or None

        (payload,) = await eventually(received)
    finally:
        await listener.close()

    notification = json.loads(payload)
    assert notification == {
        "id": str(registered.event_id),
        "type": "identity.customer.registered",
        "audience": ["staff"],
        "occurred_at": NOW.isoformat(),
        "data": {"account_id": str(account.id), "display_name": "Erika"},
        "truncated": False,
    }
