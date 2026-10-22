"""Realtime delivery of domain events to browsers via Server-Sent Events.

The worker publishes events with an audience through ``NOTIFY mb_events`` once
they are processed. Every API process runs one :class:`RealtimeHub` that listens
on that channel and fans the events out to the SSE streams of its connected
clients. A client that reconnects with ``Last-Event-ID`` gets what it missed
replayed from the outbox.
"""

import asyncio
import contextlib
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Annotated, Any, Final
from uuid import UUID

import asyncpg
import structlog
from fastapi import APIRouter, Header, params
from fastapi.sse import EventSourceResponse, ServerSentEvent
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine

from modellbahn.platform.events import EventRegistry, UnknownEventTypeError
from modellbahn.platform.outbox import EVENTS_CHANNEL, OutboxStatus, RealtimeEvent, outbox_table

REPLAY_LIMIT: Final = 100
DEFAULT_QUEUE_SIZE: Final = 256

_CONNECTION_ERRORS: Final = (OSError, asyncpg.PostgresError, asyncpg.InterfaceError)

_logger = structlog.get_logger(__name__)


class RealtimeEventData(BaseModel):
    """The JSON in the ``data:`` field of every SSE message."""

    id: UUID
    type: str
    occurred_at: datetime
    data: dict[str, Any]
    truncated: bool
    """True if ``data`` was too large for a notification and has been left out."""


def to_server_sent_event(event: RealtimeEvent) -> ServerSentEvent:
    """One SSE frame: ``id`` = event id, ``event`` = event type, ``data`` = JSON."""
    body = RealtimeEventData(
        id=event.id,
        type=event.type,
        occurred_at=event.occurred_at,
        data=event.data,
        truncated=event.truncated,
    )
    return ServerSentEvent(id=str(event.id), event=event.type, raw_data=body.model_dump_json())


@dataclass(eq=False)
class Subscription:
    """One SSE client's view of the hub: a bounded queue of events for its audience.

    A slow client loses its oldest events rather than stalling the hub or
    growing memory without bound.
    """

    audience: str
    queue: asyncio.Queue[RealtimeEvent | None] = field(
        default_factory=lambda: asyncio.Queue(maxsize=DEFAULT_QUEUE_SIZE)
    )
    dropped: int = 0

    def offer(self, event: RealtimeEvent) -> None:
        """Queue ``event`` if it addresses this audience, dropping the oldest if full."""
        if self.audience not in event.audience:
            return
        if self.queue.full():
            self.queue.get_nowait()
            self.dropped += 1
        self.queue.put_nowait(event)

    def close(self) -> None:
        """End the stream; the client reconnects and catches up via replay."""
        if self.queue.full():
            self.queue.get_nowait()
        self.queue.put_nowait(None)

    async def __aiter__(self) -> AsyncIterator[RealtimeEvent]:
        while (event := await self.queue.get()) is not None:
            yield event


class RealtimeHub:
    """Listens on ``mb_events`` and fans events out to in-process subscribers.

    The listening connection is supervised: if it breaks, every subscription is
    closed (clients reconnect with ``Last-Event-ID`` and get the gap replayed) and
    the hub reconnects with back-off.
    """

    def __init__(
        self,
        dsn: str,
        *,
        health_check_seconds: float = 30.0,
        reconnect_delay_seconds: float = 1.0,
        max_reconnect_delay_seconds: float = 30.0,
    ) -> None:
        self._dsn = dsn
        self._health_check_seconds = health_check_seconds
        self._reconnect_delay = reconnect_delay_seconds
        self._max_reconnect_delay = max_reconnect_delay_seconds
        self._subscriptions: set[Subscription] = set()
        self._listening = asyncio.Event()
        self._supervisor: asyncio.Task[None] | None = None

    @property
    def is_listening(self) -> bool:
        """True while the ``LISTEN`` connection is up."""
        return self._listening.is_set()

    @property
    def subscriber_count(self) -> int:
        """Number of connected SSE clients in this process."""
        return len(self._subscriptions)

    async def start(self, *, wait_seconds: float = 5.0) -> None:
        """Start listening. Waits briefly for the connection but never fails on it."""
        if self._supervisor is None:
            self._supervisor = asyncio.create_task(self._supervise(), name="realtime-hub")
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(self._listening.wait(), timeout=wait_seconds)

    async def stop(self) -> None:
        """Stop listening and end every open stream."""
        if self._supervisor is not None:
            self._supervisor.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._supervisor
            self._supervisor = None
        self._close_subscriptions()

    @contextlib.asynccontextmanager
    async def subscribe(self, audience: str) -> AsyncIterator[Subscription]:
        """Receive the events for ``audience`` while the context is open."""
        subscription = Subscription(audience=audience)
        self._subscriptions.add(subscription)
        try:
            yield subscription
        finally:
            self._subscriptions.discard(subscription)

    def deliver(self, event: RealtimeEvent) -> None:
        """Hand ``event`` to every subscription whose audience it addresses."""
        for subscription in tuple(self._subscriptions):
            subscription.offer(event)

    async def _supervise(self) -> None:
        delay = self._reconnect_delay
        while True:
            try:
                connection = await asyncpg.connect(self._dsn)
            except _CONNECTION_ERRORS as exc:
                _logger.warning("realtime.listener.connect_failed", error=str(exc), retry_in=delay)
                await asyncio.sleep(delay)
                delay = min(delay * 2, self._max_reconnect_delay)
                continue
            delay = self._reconnect_delay
            try:
                await self._listen(connection)
            except _CONNECTION_ERRORS as exc:
                _logger.warning("realtime.listener.lost", error=str(exc))
            except Exception:
                # A bug must not silently end realtime delivery for the process' lifetime.
                _logger.exception("realtime.listener.crashed")
                await asyncio.sleep(delay)
            finally:
                self._listening.clear()
                self._close_subscriptions()
                with contextlib.suppress(Exception):
                    await connection.close(timeout=5)

    async def _listen(self, connection: asyncpg.Connection) -> None:
        lost = asyncio.Event()
        connection.add_termination_listener(lambda _connection: lost.set())
        await connection.add_listener(EVENTS_CHANNEL, self._on_notify)
        self._listening.set()
        _logger.info("realtime.listener.started")
        while not lost.is_set():
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(lost.wait(), timeout=self._health_check_seconds)
            if not lost.is_set():
                # A half-open TCP connection would otherwise go unnoticed forever.
                await connection.execute("SELECT 1", timeout=self._health_check_seconds)
        _logger.warning("realtime.listener.terminated")

    def _on_notify(self, connection: object, pid: int, channel: str, payload: object) -> None:
        try:
            event = RealtimeEvent.from_notification(str(payload))
        except (ValueError, KeyError, TypeError) as exc:
            _logger.warning("realtime.notification.malformed", error=str(exc))
            return
        self.deliver(event)

    def _close_subscriptions(self) -> None:
        for subscription in tuple(self._subscriptions):
            subscription.close()


async def replay_events(
    engine: AsyncEngine, registry: EventRegistry, *, audience: str, after: UUID
) -> list[RealtimeEvent]:
    """Published events for ``audience`` with an id greater than ``after`` (oldest first)."""
    event_types = registry.event_types_for(audience)
    if not event_types:
        return []
    statement = (
        select(outbox_table)
        .where(
            outbox_table.c.status == OutboxStatus.PUBLISHED,
            outbox_table.c.id > after,
            outbox_table.c.event_type.in_(event_types),
        )
        .order_by(outbox_table.c.id)
        .limit(REPLAY_LIMIT)
    )
    async with engine.connect() as connection:
        rows = (await connection.execute(statement)).all()
    events: list[RealtimeEvent] = []
    for row in rows:
        try:
            event = registry.deserialize(
                row.event_type,
                event_id=row.id,
                aggregate_id=row.aggregate_id,
                occurred_at=row.occurred_at,
                payload=row.payload,
            )
        except (UnknownEventTypeError, KeyError, TypeError, ValueError) as exc:
            # An old row the current code cannot read must not break the stream.
            _logger.warning("realtime.replay.skipped", event_id=str(row.id), error=str(exc))
            continue
        events.append(RealtimeEvent.from_domain_event(event))
    return events


def create_event_stream_router(
    *,
    hub: RealtimeHub,
    engine: AsyncEngine,
    registry: EventRegistry,
    audience: str,
    path: str,
    operation_id: str,
    tags: Sequence[str],
    dependencies: Sequence[params.Depends],
    responses: dict[int | str, dict[str, Any]] | None = None,
) -> APIRouter:
    """Router with one SSE endpoint streaming the events of ``audience``.

    Access control is the caller's job (``dependencies``), which keeps this
    module free of any knowledge about accounts.
    """
    router = APIRouter(tags=list(tags), dependencies=list(dependencies))

    @router.get(
        path,
        operation_id=operation_id,
        response_class=EventSourceResponse,
        responses=responses,
        summary=f"Live stream of events for the {audience!r} audience",
        description=(
            "Server-Sent Events. Each message has `id` (event id, UUIDv7), `event` (event type) "
            "and `data` (JSON, see RealtimeEventData). A comment line is sent every 15 seconds "
            "as a heartbeat. Reconnecting with `Last-Event-ID` replays up to 100 missed events."
        ),
    )
    async def stream_events(
        last_event_id: Annotated[str | None, Header(alias="Last-Event-ID")] = None,
    ) -> AsyncIterator[RealtimeEventData]:
        # The annotation documents the JSON inside `data:` in the OpenAPI schema. The
        # frames themselves are ServerSentEvent objects (to set `id` and `event`),
        # which FastAPI streams as they are; hence the ignores on the yields.
        async with hub.subscribe(audience) as subscription:
            # Subscribe before replaying so nothing published meanwhile is lost;
            # events seen in the replay are skipped when they arrive live.
            replayed: set[UUID] = set()
            after = _parse_event_id(last_event_id)
            if after is not None:
                for event in await replay_events(engine, registry, audience=audience, after=after):
                    replayed.add(event.id)
                    yield to_server_sent_event(event)  # type: ignore[misc]
            async for event in subscription:
                if event.id not in replayed:
                    yield to_server_sent_event(event)  # type: ignore[misc]

    return router


def _parse_event_id(value: str | None) -> UUID | None:
    if not value:
        return None
    try:
        return UUID(value.strip())
    except ValueError:
        return None
