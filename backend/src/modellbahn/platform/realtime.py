"""Realtime delivery of domain events to browsers via Server-Sent Events.

The worker publishes events with an audience through ``NOTIFY mb_events`` once
they are processed. Every API process runs one :class:`RealtimeHub` that listens
on that channel and fans the events out to the SSE streams of its connected
clients. A client that reconnects with ``Last-Event-ID`` (or, for a new
``EventSource``, the ``last_event_id`` query parameter) gets what it missed
replayed from the outbox, in the order the events were published.
"""

import asyncio
import contextlib
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Annotated, Any, Final
from uuid import UUID

import asyncpg
import structlog
from fastapi import APIRouter, Header, Query, Request, params
from fastapi.sse import EventSourceResponse, ServerSentEvent
from pydantic import BaseModel
from sqlalchemy import ColumnElement, select, tuple_
from sqlalchemy.ext.asyncio import AsyncEngine

from modellbahn.platform.db import is_database_unavailable
from modellbahn.platform.events import EventRegistry, UnknownEventTypeError
from modellbahn.platform.outbox import EVENTS_CHANNEL, OutboxStatus, RealtimeEvent, outbox_table

REPLAY_LIMIT: Final = 100
DEFAULT_QUEUE_SIZE: Final = 256
AUTHORIZATION_CHECK_SECONDS: Final = 15.0
"""How often an open stream re-checks that its client may still receive events."""
BEGINNING: Final = UUID(int=0)
"""A replay cursor that comes before every event."""

_CONNECTION_ERRORS: Final = (OSError, asyncpg.PostgresError, asyncpg.InterfaceError)

_logger = structlog.get_logger(__name__)

type Authorize = Callable[[Request], Awaitable[bool]]
"""Whether the client of a stream may (still) receive the events of its audience."""


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
    growing memory without bound. ``live`` is set while the hub listens, i.e.
    once no event of the audience can pass the subscription by any more.
    """

    audience: str
    queue: asyncio.Queue[RealtimeEvent | None] = field(
        default_factory=lambda: asyncio.Queue(maxsize=DEFAULT_QUEUE_SIZE)
    )
    dropped: int = 0
    live: asyncio.Event = field(default_factory=asyncio.Event)
    _closed: bool = field(default=False, init=False)

    @property
    def closed(self) -> bool:
        """True once :meth:`close` was called; the stream should end."""
        return self._closed

    def offer(self, event: RealtimeEvent) -> None:
        """Queue ``event`` if it addresses this audience, dropping the oldest if full."""
        if self.closed or self.audience not in event.audience:
            return
        if self.queue.full():
            self.queue.get_nowait()
            self.dropped += 1
        self.queue.put_nowait(event)

    def close(self) -> None:
        """End the stream; the client reconnects and catches up via replay."""
        if self._closed:
            return
        self._closed = True
        if self.queue.full():
            self.queue.get_nowait()
        self.queue.put_nowait(None)
        # Wakes a stream that is still waiting for the hub to listen.
        self.live.set()

    async def next(self, *, within: float) -> RealtimeEvent | None:
        """The next event; ``None`` if none came ``within`` seconds or the subscription closed."""
        try:
            async with asyncio.timeout(within):
                return await self.queue.get()
        except TimeoutError:
            return None

    async def wait_live(self, *, within: float) -> bool:
        """Wait until the hub listens (or the subscription closes); False if it takes longer."""
        try:
            async with asyncio.timeout(within):
                await self.live.wait()
        except TimeoutError:
            return False
        return True

    async def __aiter__(self) -> AsyncIterator[RealtimeEvent]:
        while (event := await self.queue.get()) is not None:
            yield event


class RealtimeHub:
    """Listens on ``mb_events`` and fans events out to in-process subscribers.

    The listening connection is supervised: if it breaks, every subscription is
    closed (clients reconnect with ``Last-Event-ID`` and get the gap replayed) and
    the hub reconnects with back-off. Subscriptions made while it does not listen
    become live once it does; their streams replay what was published meanwhile.
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
        self._closing = False
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
        self._closing = False
        if self._supervisor is None:
            self._supervisor = asyncio.create_task(self._supervise(), name="realtime-hub")
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(self._listening.wait(), timeout=wait_seconds)

    def close_streams(self) -> None:
        """End every open stream and refuse new ones, e.g. because the server shuts down.

        Uvicorn waits for open responses to finish before it runs the lifespan
        shutdown, and a stream does not finish on its own.
        """
        self._closing = True
        self._close_subscriptions()

    async def stop(self) -> None:
        """Stop listening and end every open stream."""
        self.close_streams()
        if self._supervisor is not None:
            self._supervisor.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._supervisor
            self._supervisor = None

    @contextlib.asynccontextmanager
    async def subscribe(self, audience: str) -> AsyncIterator[Subscription]:
        """Receive the events for ``audience`` while the context is open."""
        subscription = Subscription(audience=audience)
        if self._closing:
            subscription.close()
        elif self.is_listening:
            subscription.live.set()
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
        for subscription in tuple(self._subscriptions):
            subscription.live.set()
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
    """Events for ``audience`` published after the event ``after``, in publication order.

    Publication order differs from the order of the (time-ordered) ids when an event
    is published late, e.g. after a retry, so the cursor is the publication time of
    ``after``. An id that is not (or no longer) in the outbox, like :data:`BEGINNING`,
    falls back to comparing ids. Returns at most :data:`REPLAY_LIMIT` events.
    """
    event_types = registry.event_types_for(audience)
    if not event_types:
        return []
    columns = outbox_table.c
    async with engine.connect() as connection:
        published_at = await connection.scalar(
            select(columns.published_at).where(
                columns.id == after, columns.status == OutboxStatus.PUBLISHED
            )
        )
        position: ColumnElement[bool] = (
            columns.id > after
            if published_at is None
            else tuple_(columns.published_at, columns.id) > tuple_(published_at, after)
        )
        rows = (
            await connection.execute(
                select(outbox_table)
                .where(
                    columns.status == OutboxStatus.PUBLISHED,
                    columns.event_type.in_(event_types),
                    position,
                )
                .order_by(columns.published_at, columns.id)
                .limit(REPLAY_LIMIT)
            )
        ).all()
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


async def latest_event_id(engine: AsyncEngine, registry: EventRegistry, *, audience: str) -> UUID:
    """The id of the event last published for ``audience``; :data:`BEGINNING` if none."""
    event_types = registry.event_types_for(audience)
    if not event_types:
        return BEGINNING
    columns = outbox_table.c
    async with engine.connect() as connection:
        latest = await connection.scalar(
            select(columns.id)
            .where(columns.status == OutboxStatus.PUBLISHED, columns.event_type.in_(event_types))
            .order_by(columns.published_at.desc(), columns.id.desc())
            .limit(1)
        )
    return latest or BEGINNING


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
    authorize: Authorize,
    authorization_check_seconds: float = AUTHORIZATION_CHECK_SECONDS,
    responses: dict[int | str, dict[str, Any]] | None = None,
) -> APIRouter:
    """Router with one SSE endpoint streaming the events of ``audience``.

    Access control is the caller's job, which keeps this module free of any
    knowledge about accounts: ``dependencies`` guard the request (and answer it
    with an error), ``authorize`` is asked again before every event and every
    ``authorization_check_seconds`` while the stream is open, so that a logout or
    an expired session ends it.
    """
    router = APIRouter(tags=list(tags), dependencies=list(dependencies))

    async def still_authorized(request: Request) -> bool:
        try:
            return await authorize(request)
        except Exception as exc:
            # E.g. the database has gone away. The client reconnects and is checked anew.
            _logger.warning(
                "realtime.stream.authorization_failed", error=f"{type(exc).__name__}: {exc}"
            )
            return False

    @router.get(
        path,
        operation_id=operation_id,
        response_class=EventSourceResponse,
        responses=responses,
        summary=f"Live stream of events for the {audience!r} audience",
        description=(
            "Server-Sent Events. Each message has `id` (event id, UUIDv7), `event` (event type) "
            "and `data` (JSON, see RealtimeEventData). A comment line is sent every 15 seconds "
            "as a heartbeat. Reconnecting with `Last-Event-ID` (or `last_event_id`, for a new "
            "EventSource) replays up to 100 missed events in publication order. The stream "
            "ends when the session ends."
        ),
    )
    async def stream_events(
        request: Request,
        last_event_id_header: Annotated[str | None, Header(alias="Last-Event-ID")] = None,
        last_event_id: Annotated[
            str | None,
            Query(
                description=(
                    "The id of the last event received, for a new EventSource (which cannot "
                    "send Last-Event-ID). The header wins if both are present."
                )
            ),
        ] = None,
    ) -> AsyncIterator[RealtimeEventData]:
        # The annotation documents the JSON inside `data:` in the OpenAPI schema. The
        # frames themselves are ServerSentEvent objects (to set `id` and `event`),
        # which FastAPI streams as they are; hence the ignores on the yields.
        after = _parse_event_id(last_event_id_header) or _parse_event_id(last_event_id)
        try:
            async with hub.subscribe(audience) as subscription:
                # Subscribe before replaying so nothing published meanwhile is lost;
                # events seen in the replay are skipped when they arrive live.
                if not subscription.live.is_set():
                    # The hub does not listen right now, so events published until it
                    # does never reach this subscription: replay them from here on.
                    after = after or await latest_event_id(engine, registry, audience=audience)
                    while not await subscription.wait_live(within=authorization_check_seconds):
                        if not await still_authorized(request):
                            return
                replayed: set[UUID] = set()
                if after is not None and not subscription.closed:
                    for event in await replay_events(
                        engine, registry, audience=audience, after=after
                    ):
                        replayed.add(event.id)
                        yield to_server_sent_event(event)  # type: ignore[misc]
                while True:
                    # None means a timeout or a closed subscription. Either way, and
                    # before every event, the client must still be authorized.
                    received = await subscription.next(within=authorization_check_seconds)
                    if subscription.closed or not await still_authorized(request):
                        return
                    if received is not None and received.id not in replayed:
                        yield to_server_sent_event(received)  # type: ignore[misc]
        except Exception as exc:
            if not is_database_unavailable(exc):
                raise
            _logger.warning(
                "realtime.stream.database_unavailable", error=f"{type(exc).__name__}: {exc}"
            )

    return router


def _parse_event_id(value: str | None) -> UUID | None:
    if not value:
        return None
    try:
        return UUID(value.strip())
    except ValueError:
        return None
