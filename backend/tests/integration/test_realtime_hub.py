"""The realtime hub (LISTEN mb_events) and the replay from the outbox."""

import asyncio
import json
from collections.abc import AsyncIterator
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from modellbahn.modules.identity.application.services import UnitOfWorkFactory
from modellbahn.modules.identity.domain.model import Account
from modellbahn.platform.config import Settings
from modellbahn.platform.db import asyncpg_dsn
from modellbahn.platform.events import event_registry
from modellbahn.platform.outbox import HandlerRegistry, OutboxDispatcher, RealtimeEvent
from modellbahn.platform.realtime import (
    BEGINNING,
    RealtimeHub,
    Subscription,
    latest_event_id,
    replay_events,
)
from tests.support import NOW, eventually


@pytest.fixture
async def hub(settings: Settings) -> AsyncIterator[RealtimeHub]:
    hub = RealtimeHub(asyncpg_dsn(settings.database_url), reconnect_delay_seconds=0.05)
    await hub.start()
    assert hub.is_listening
    yield hub
    await hub.stop()


async def notify(engine: AsyncEngine, payload: str) -> None:
    async with engine.begin() as connection:
        await connection.execute(
            text("SELECT pg_notify('mb_events', :payload)"), {"payload": payload}
        )


def staff_event(audience: str = "staff") -> RealtimeEvent:
    return RealtimeEvent(
        id=uuid4(),
        type="identity.customer.registered",
        audience=frozenset({audience}),
        occurred_at=NOW,
        data={"display_name": "Erika"},
    )


async def next_event(subscription: Subscription) -> RealtimeEvent | None:
    async with asyncio.timeout(5):
        return await subscription.queue.get()


async def test_delivers_notifications_to_matching_subscribers(
    hub: RealtimeHub, engine: AsyncEngine
) -> None:
    async with hub.subscribe("staff") as staff, hub.subscribe("customers") as customers:
        assert hub.subscriber_count == 2
        await notify(engine, "not json")
        await notify(engine, json.dumps({"id": "broken"}))
        event = staff_event()
        await notify(engine, event.to_notification())

        assert await next_event(staff) == event
        assert customers.queue.empty()
    assert hub.subscriber_count == 0


async def test_stop_ends_every_stream(settings: Settings) -> None:
    hub = RealtimeHub(asyncpg_dsn(settings.database_url))
    await hub.start()
    async with hub.subscribe("staff") as subscription:
        await hub.stop()
        assert [event async for event in subscription] == []
    assert not hub.is_listening


async def test_reconnects_after_losing_the_connection(
    hub: RealtimeHub, engine: AsyncEngine
) -> None:
    async with hub.subscribe("staff") as subscription:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = current_database() AND query LIKE 'LISTEN%'"
                )
            )
        # Streams end, so that clients reconnect and catch up through replay.
        async with asyncio.timeout(5):
            assert [event async for event in subscription] == []

    async def listening() -> bool | None:
        return True if hub.is_listening else None

    await eventually(listening)
    async with hub.subscribe("staff") as subscription:
        event = staff_event()
        await notify(engine, event.to_notification())
        assert await next_event(subscription) == event


async def test_start_does_not_fail_without_database() -> None:
    hub = RealtimeHub("postgresql://nobody:secret@127.0.0.1:1/nothing")
    await hub.start(wait_seconds=0.2)
    assert not hub.is_listening
    await hub.stop()


async def test_replay_returns_published_audience_events_after_an_id(
    engine: AsyncEngine, uow_factory: UnitOfWorkFactory, settings: Settings
) -> None:
    registered = []
    for index in range(3):
        account, event = Account.register_customer(
            email=f"kunde{index}@example.com",
            display_name=f"Kunde {index}",
            password_hash="h",
            now=NOW,
        )
        async with uow_factory() as uow:
            uow.accounts.add(account)
            uow.publish(event, account.note_registration_attempt(NOW))
            await uow.commit()
        registered.append(event)

    # Pending events are not replayed yet.
    assert (
        await replay_events(engine, event_registry, audience="staff", after=registered[0].event_id)
        == []
    )

    dispatcher = OutboxDispatcher(
        engine=engine,
        listen_dsn=asyncpg_dsn(settings.database_url),
        events=event_registry,
        handlers=HandlerRegistry(),
        poll_seconds=1,
        max_attempts=3,
    )
    await dispatcher.dispatch_batch()

    replayed = await replay_events(
        engine, event_registry, audience="staff", after=registered[0].event_id
    )
    # Only staff-audience events, oldest first; registration attempts have no audience.
    assert [event.id for event in replayed] == [e.event_id for e in registered[1:]]
    assert replayed[0].data == {
        "account_id": str(registered[1].aggregate_id),
        "display_name": "Kunde 1",
    }
    assert await replay_events(engine, event_registry, audience="nobody", after=uuid4()) == []


async def insert_published(
    engine: AsyncEngine, event_id: UUID, *, published_minutes_ago: int, name: str
) -> None:
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "INSERT INTO platform.outbox (id, event_type, aggregate_type, aggregate_id, "
                "payload, occurred_at, status, published_at) VALUES (:id, "
                "'identity.customer.registered', 'identity.account', :account, "
                "CAST(:payload AS jsonb), now(), 'published', "
                "now() - make_interval(mins => :minutes))"
            ),
            {
                "id": event_id,
                "account": uuid4(),
                "payload": json.dumps({"account_id": str(uuid4()), "display_name": name}),
                "minutes": published_minutes_ago,
            },
        )


async def test_replay_follows_publication_order_not_the_ids(engine: AsyncEngine) -> None:
    # The event with the smaller id was published later, e.g. after a retry. A client
    # that already saw the other one must still get it.
    older_id, newer_id = UUID(int=1), UUID(int=2)
    await insert_published(engine, newer_id, published_minutes_ago=5, name="Zuerst veröffentlicht")
    await insert_published(engine, older_id, published_minutes_ago=1, name="Später veröffentlicht")

    after_newer = await replay_events(engine, event_registry, audience="staff", after=newer_id)
    assert [event.id for event in after_newer] == [older_id]
    assert await replay_events(engine, event_registry, audience="staff", after=older_id) == []
    # An id the outbox does not know (e.g. purged) falls back to comparing ids.
    from_start = await replay_events(engine, event_registry, audience="staff", after=BEGINNING)
    assert [event.id for event in from_start] == [newer_id, older_id]

    assert await latest_event_id(engine, event_registry, audience="staff") == older_id
    assert await latest_event_id(engine, event_registry, audience="nobody") == BEGINNING


async def test_subscriptions_go_live_once_the_hub_listens(settings: Settings) -> None:
    hub = RealtimeHub(asyncpg_dsn(settings.database_url), reconnect_delay_seconds=0.05)
    async with hub.subscribe("staff") as subscription:
        # Not listening yet: events published now would pass the subscription by,
        # so the stream must replay them once the hub listens.
        assert not subscription.live.is_set()
        assert not await subscription.wait_live(within=0.05)
        await hub.start()
        assert await subscription.wait_live(within=5)
        async with hub.subscribe("staff") as later:
            assert later.live.is_set()
    await hub.stop()


async def test_close_streams_ends_open_streams_and_refuses_new_ones(hub: RealtimeHub) -> None:
    async with hub.subscribe("staff") as subscription:
        hub.close_streams()
        assert subscription.closed
        assert [event async for event in subscription] == []
        # Closing twice is harmless, and events offered afterwards are ignored.
        subscription.close()
        subscription.offer(staff_event())
        assert subscription.queue.empty()
    async with hub.subscribe("staff") as late:
        assert late.closed
        assert await late.next(within=1) is None


async def test_replay_skips_rows_it_cannot_read(engine: AsyncEngine) -> None:
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "INSERT INTO platform.outbox (id, event_type, aggregate_type, aggregate_id, "
                "payload, occurred_at, status, published_at) VALUES (:id, "
                "'identity.customer.registered', 'identity.account', :id, '{}', "
                "now(), 'published', now())"
            ),
            # The payload lacks the display name this event type requires.
            {"id": uuid4()},
        )
    after = UUID(int=0)
    assert await replay_events(engine, event_registry, audience="staff", after=after) == []
