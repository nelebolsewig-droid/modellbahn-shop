"""Transactional outbox: table, handler registry and the dispatcher run by the worker.

Events are written to ``platform.outbox`` in the same transaction as the state
change that caused them (see :class:`~modellbahn.platform.uow.UnitOfWork`). The
worker's :class:`OutboxDispatcher` later hands them to the registered handlers
and, for events with a realtime audience, forwards them to the API processes via
``NOTIFY mb_events``.
"""

import asyncio
import contextlib
import json
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any, Final, Self
from uuid import UUID

import asyncpg
import structlog
from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    Index,
    Row,
    SmallInteger,
    Table,
    Text,
    Uuid,
    delete,
    func,
    select,
    text,
    update,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from modellbahn.platform.db import metadata
from modellbahn.platform.events import DomainEvent, EventRegistry, JsonObject

OUTBOX_CHANNEL: Final = "mb_outbox"
EVENTS_CHANNEL: Final = "mb_events"
# PostgreSQL rejects NOTIFY payloads of 8000 bytes or more; stay clear of the limit.
MAX_NOTIFICATION_BYTES: Final = 7900
DEFAULT_BATCH_SIZE: Final = 20
RETRY_BASE_DELAY: Final = timedelta(seconds=30)
RETRY_MAX_DELAY: Final = timedelta(hours=1)
LAST_ERROR_MAX_LENGTH: Final = 2000
# Published events serve the realtime replay and debugging; after that they only
# keep personal data around.
PUBLISHED_RETENTION: Final = timedelta(days=30)
PURGE_INTERVAL_SECONDS: Final = 3600.0
LISTENER_CHECK_INTERVAL_SECONDS: Final = 30.0
LISTENER_CHECK_TIMEOUT_SECONDS: Final = 5.0

_logger = structlog.get_logger(__name__)


# Database errors (an outage, typically): the loop logs them and tries again later.
_DATABASE_UNAVAILABLE: Final = (OSError, DBAPIError, asyncpg.PostgresError, asyncpg.InterfaceError)


class OutboxStatus(StrEnum):
    """Lifecycle of an outbox row: ``pending`` until handled, then ``published`` or ``dead``."""

    PENDING = "pending"
    PUBLISHED = "published"
    DEAD = "dead"


outbox_table = Table(
    "outbox",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("event_type", Text, nullable=False),
    Column("aggregate_type", Text, nullable=False),
    Column("aggregate_id", Uuid, nullable=False),
    Column("payload", JSONB, nullable=False),
    Column("occurred_at", DateTime(timezone=True), nullable=False),
    Column("status", Text, nullable=False, server_default=text("'pending'")),
    Column("attempts", SmallInteger, nullable=False, server_default=text("0")),
    Column("next_attempt_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("published_at", DateTime(timezone=True)),
    Column("last_error", Text),
    # Handlers that already succeeded for this event; a retry runs only the others.
    Column("handled_by", ARRAY(Text), nullable=False, server_default=text("'{}'")),
    CheckConstraint("status IN ('pending', 'published', 'dead')", name="status"),
    CheckConstraint("attempts >= 0", name="attempts_non_negative"),
    CheckConstraint("(status = 'published') = (published_at IS NOT NULL)", name="published_at"),
    Index("outbox_pending_idx", "next_attempt_at", postgresql_where=text("status = 'pending'")),
    Index(
        "outbox_published_idx",
        "published_at",
        "id",
        postgresql_where=text("status = 'published'"),
    ),
    Index("outbox_aggregate_idx", "aggregate_id"),
    schema="platform",
)


@dataclass(frozen=True, slots=True)
class RealtimeEvent:
    """Notification sent on ``mb_events`` when an event with an audience was published.

    The API processes' realtime hubs turn these into Server-Sent Events.
    """

    id: UUID
    type: str
    audience: frozenset[str]
    occurred_at: datetime
    data: JsonObject
    truncated: bool = False

    @classmethod
    def from_domain_event(cls, event: DomainEvent) -> Self:
        """The notification for ``event``, carrying only its public payload."""
        return cls(
            id=event.event_id,
            type=event.event_type,
            audience=event.audience,
            occurred_at=event.occurred_at,
            data=event.public_payload(),
        )

    def to_notification(self) -> str:
        """JSON for ``pg_notify``. Oversized data is dropped and flagged instead."""
        encoded = json.dumps(self._as_json(), separators=(",", ":"), ensure_ascii=False)
        if len(encoded.encode()) < MAX_NOTIFICATION_BYTES:
            return encoded
        return replace(self, data={}, truncated=True).to_notification()

    @classmethod
    def from_notification(cls, payload: str) -> Self:
        """Parse a notification received on ``mb_events``."""
        raw = json.loads(payload)
        return cls(
            id=UUID(raw["id"]),
            type=str(raw["type"]),
            audience=frozenset(raw["audience"]),
            occurred_at=datetime.fromisoformat(raw["occurred_at"]),
            data=dict(raw["data"]),
            truncated=bool(raw.get("truncated", False)),
        )

    def _as_json(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "type": self.type,
            "audience": sorted(self.audience),
            "occurred_at": self.occurred_at.isoformat(),
            "data": self.data,
            "truncated": self.truncated,
        }


def outbox_record(event: DomainEvent) -> dict[str, Any]:
    """The outbox row for ``event``."""
    return {
        "id": event.event_id,
        "event_type": event.event_type,
        "aggregate_type": event.aggregate_type,
        "aggregate_id": event.aggregate_id,
        "payload": event.payload(),
        "occurred_at": event.occurred_at,
    }


def retry_delay(attempts: int) -> timedelta:
    """Back-off before the next attempt: 30 s · 2^(attempts-1), capped at one hour."""
    exponent = max(attempts - 1, 0)
    # Beyond 2^7 the cap applies anyway; bounding the exponent avoids huge numbers.
    return min(RETRY_BASE_DELAY * (1 << min(exponent, 16)), RETRY_MAX_DELAY)


type Handler = Callable[[DomainEvent], Awaitable[None]]


@dataclass(frozen=True, slots=True)
class RegisteredHandler:
    """A handler with the name its delivery state is kept under."""

    name: str
    handle: Handler


class HandlerRegistry:
    """Maps each event type to the handlers that react to it, each under its own name.

    Several modules may react to the same event (a paid order sends a confirmation and
    allocates stock). The outbox notes per event which handlers already succeeded
    (``handled_by``), so a retry runs only the ones that failed, and one failing
    handler does not hold back the others.

    The name defaults to the handler's qualified name, e.g.
    ``SalesHandlers.send_confirmation``. It is stored for events that are retried, so
    renaming a handler can make it run once more for such an event; delivery is at
    least once anyway.

    Delivery is **at least once**: a handler can run again for an event it already
    processed, e.g. when the worker dies after the handler finished but before the
    event was marked as published. Every handler must therefore be idempotent:
    record what it did under the event id (a unique ``source_event_id`` column is
    the usual way) or check the state it would create, and do nothing if it exists.
    Where this is impossible, such as for a plain notification e-mail, a rare
    duplicate must be acceptable.
    """

    def __init__(self) -> None:
        self._handlers: dict[str, list[RegisteredHandler]] = {}

    def register[E: DomainEvent](
        self,
        event_class: type[E],
        handler: Callable[[E], Awaitable[None]],
        *,
        name: str | None = None,
    ) -> None:
        """Run ``handler`` for every event of ``event_class``."""
        event_type = event_class.event_type
        handler_name = name or str(getattr(handler, "__qualname__", repr(handler)))
        registered = self._handlers.setdefault(event_type, [])
        if any(entry.name == handler_name for entry in registered):
            msg = f"{event_type} already has a handler named {handler_name!r}"
            raise ValueError(msg)

        async def typed_handler(event: DomainEvent) -> None:
            if not isinstance(event, event_class):
                msg = f"expected {event_class.__name__}, got {type(event).__name__}"
                raise TypeError(msg)
            await handler(event)

        registered.append(RegisteredHandler(handler_name, typed_handler))

    def handlers_for(self, event_type: str) -> list[RegisteredHandler]:
        """The handlers registered for ``event_type``, in the order of registration."""
        return list(self._handlers.get(event_type, ()))


class OutboxDispatcher:
    """Delivers outbox events to their handlers (runs in the worker process).

    Rows are claimed with ``FOR UPDATE SKIP LOCKED`` inside one transaction, so any
    number of dispatchers can run side by side without processing an event twice
    concurrently. Handlers run while the rows are locked, then the outcome is stored
    in the same transaction. The dispatcher sleeps until ``NOTIFY mb_outbox`` arrives
    or the poll interval passes; polling also picks up retries whose time has come.

    The ``LISTEN`` connection is supervised: when it breaks, the dispatcher
    reconnects at once instead of relying on the poll interval until the next
    failure surfaces. Published events are deleted after ``retention``.
    """

    def __init__(
        self,
        *,
        engine: AsyncEngine,
        listen_dsn: str,
        events: EventRegistry,
        handlers: HandlerRegistry,
        poll_seconds: float,
        max_attempts: int,
        batch_size: int = DEFAULT_BATCH_SIZE,
        retention: timedelta = PUBLISHED_RETENTION,
    ) -> None:
        self._engine = engine
        self._listen_dsn = listen_dsn
        self._events = events
        self._handlers = handlers
        self._poll_seconds = poll_seconds
        self._max_attempts = max_attempts
        self._batch_size = batch_size
        self._retention = retention
        self._wakeup = asyncio.Event()
        self._listener: asyncpg.Connection | None = None
        self._listener_checked_at = 0.0
        self._purged_at: float | None = None

    async def run(self, stop: asyncio.Event) -> None:
        """Dispatch until ``stop`` is set.

        A handler that is running is allowed to finish; the rest of its batch stays
        pending for the next start.
        """
        _logger.info("outbox.dispatcher.started")
        try:
            while not stop.is_set():
                await self._ensure_listener()
                self._wakeup.clear()
                try:
                    processed = await self.dispatch_batch(stop)
                    await self._purge_if_due()
                except _DATABASE_UNAVAILABLE as exc:
                    _logger.warning("outbox.dispatch.database_error", error=str(exc))
                    processed = 0
                if processed < self._batch_size and not await self._sleep(stop):
                    await self._check_listener()
        finally:
            await self._close_listener()
            _logger.info("outbox.dispatcher.stopped")

    async def dispatch_batch(self, stop: asyncio.Event | None = None) -> int:
        """Claim up to ``batch_size`` due events and process them; return how many.

        Once ``stop`` is set, no further row of the batch is started. The outcome of
        the rows processed so far is committed; the others are released unchanged.
        """
        processed = 0
        async with self._engine.begin() as connection:
            rows = (
                await connection.execute(
                    select(outbox_table)
                    .where(
                        outbox_table.c.status == OutboxStatus.PENDING,
                        outbox_table.c.next_attempt_at <= func.now(),
                    )
                    .order_by(outbox_table.c.id)
                    .limit(self._batch_size)
                    .with_for_update(skip_locked=True)
                )
            ).all()
            for row in rows:
                if stop is not None and stop.is_set():
                    break
                await self._process(connection, row)
                processed += 1
        return processed

    async def purge_published(self) -> int:
        """Delete published events older than the retention period; return how many.

        Pending and dead events stay: the first still have to be delivered, the
        others need someone to look at them.
        """
        async with self._engine.begin() as connection:
            result = await connection.execute(
                delete(outbox_table).where(
                    outbox_table.c.status == OutboxStatus.PUBLISHED,
                    outbox_table.c.published_at < func.now() - self._retention,
                )
            )
        return result.rowcount

    async def _process(self, connection: AsyncConnection, row: Row[Any]) -> None:
        log: structlog.stdlib.BoundLogger = _logger.bind(
            event_id=str(row.id), event_type=row.event_type
        )
        handled: list[str] = list(row.handled_by)
        try:
            event = self._events.deserialize(
                row.event_type,
                event_id=row.id,
                aggregate_id=row.aggregate_id,
                occurred_at=row.occurred_at,
                payload=row.payload,
            )
        except Exception as exc:
            await self._record_failure(connection, row, [("deserialize", exc)], handled, log)
            return
        failures: list[tuple[str, Exception]] = []
        for registered in self._handlers.handlers_for(row.event_type):
            if registered.name in handled:
                continue
            try:
                await registered.handle(event)
            except Exception as exc:
                # The others still run: one failing handler does not hold them back.
                failures.append((registered.name, exc))
            else:
                handled.append(registered.name)
        if failures:
            await self._record_failure(connection, row, failures, handled, log)
            return

        # The wall-clock time of this statement, not of the transaction start: the
        # realtime replay orders by it, and a batch publishes its rows one by one.
        await connection.execute(
            update(outbox_table)
            .where(outbox_table.c.id == row.id)
            .values(
                status=OutboxStatus.PUBLISHED,
                published_at=func.clock_timestamp(),
                last_error=None,
                handled_by=handled,
            )
        )
        if event.audience:
            notification = RealtimeEvent.from_domain_event(event).to_notification()
            await connection.execute(select(func.pg_notify(EVENTS_CHANNEL, notification)))
        log.info("outbox.event.published", attempts=row.attempts)

    async def _record_failure(
        self,
        connection: AsyncConnection,
        row: Row[Any],
        failures: list[tuple[str, Exception]],
        handled: list[str],
        log: structlog.stdlib.BoundLogger,
    ) -> None:
        attempts = row.attempts + 1
        error = "; ".join(f"{name}: {type(exc).__name__}: {exc}" for name, exc in failures)[
            :LAST_ERROR_MAX_LENGTH
        ]
        values: dict[str, Any] = {"attempts": attempts, "last_error": error, "handled_by": handled}
        failed = [name for name, _ in failures]
        first_error = failures[0][1]
        if attempts >= self._max_attempts:
            values["status"] = OutboxStatus.DEAD
            log.error("outbox.event.dead", attempts=attempts, handlers=failed, exc_info=first_error)
        else:
            delay = retry_delay(attempts)
            values["next_attempt_at"] = func.now() + delay
            log.warning(
                "outbox.event.retry_scheduled",
                attempts=attempts,
                handlers=failed,
                retry_in_seconds=delay.total_seconds(),
                exc_info=first_error,
            )
        await connection.execute(
            update(outbox_table).where(outbox_table.c.id == row.id).values(**values)
        )

    async def _purge_if_due(self) -> None:
        now = time.monotonic()
        if self._purged_at is not None and now - self._purged_at < PURGE_INTERVAL_SECONDS:
            return
        self._purged_at = now
        deleted = await self.purge_published()
        if deleted:
            _logger.info("outbox.purged", deleted=deleted, retention_days=self._retention.days)

    async def _sleep(self, stop: asyncio.Event) -> bool:
        """Wait for a notification, ``stop`` or the poll interval; False on a timeout."""
        waiters = {
            asyncio.ensure_future(self._wakeup.wait()),
            asyncio.ensure_future(stop.wait()),
        }
        try:
            done, _ = await asyncio.wait(
                waiters, timeout=self._poll_seconds, return_when=asyncio.FIRST_COMPLETED
            )
        finally:
            for waiter in waiters:
                waiter.cancel()
        return bool(done)

    async def _ensure_listener(self) -> None:
        if self._listener is not None and not self._listener.is_closed():
            return
        self._listener = None
        try:
            listener = await asyncpg.connect(self._listen_dsn)
        except _DATABASE_UNAVAILABLE as exc:
            # Polling keeps the outbox moving; the next loop retries the LISTEN.
            _logger.warning("outbox.listener.unavailable", error=str(exc))
            return
        try:
            listener.add_termination_listener(self._on_listener_lost)
            await listener.add_listener(OUTBOX_CHANNEL, self._on_notify)
        except _DATABASE_UNAVAILABLE as exc:
            _logger.warning("outbox.listener.unavailable", error=str(exc))
            self._discard(listener)
            return
        self._listener = listener
        self._listener_checked_at = time.monotonic()

    async def _check_listener(self) -> None:
        """Replace a LISTEN connection that no longer answers (e.g. half-open TCP)."""
        listener = self._listener
        if listener is None or listener.is_closed():
            return
        if time.monotonic() - self._listener_checked_at < LISTENER_CHECK_INTERVAL_SECONDS:
            return
        try:
            await listener.execute("SELECT 1", timeout=LISTENER_CHECK_TIMEOUT_SECONDS)
        except _DATABASE_UNAVAILABLE as exc:
            _logger.warning("outbox.listener.unresponsive", error=str(exc))
            self._discard(listener)
            self._listener = None
            return
        self._listener_checked_at = time.monotonic()

    async def _close_listener(self) -> None:
        listener, self._listener = self._listener, None
        if listener is not None:
            listener.remove_termination_listener(self._on_listener_lost)
            with contextlib.suppress(*_DATABASE_UNAVAILABLE):
                await listener.close(timeout=5)

    def _discard(self, listener: asyncpg.Connection) -> None:
        listener.remove_termination_listener(self._on_listener_lost)
        listener.terminate()

    def _on_listener_lost(self, connection: object) -> None:
        # Notifications sent from now on would be missed: reconnect right away. The
        # batch after the reconnect picks up whatever was committed in between.
        _logger.warning("outbox.listener.lost")
        self._wakeup.set()

    def _on_notify(self, connection: object, pid: int, channel: str, payload: object) -> None:
        self._wakeup.set()
