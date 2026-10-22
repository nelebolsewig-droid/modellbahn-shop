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
from collections import defaultdict
from collections.abc import Awaitable, Callable, Sequence
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
    func,
    select,
    text,
    update,
)
from sqlalchemy.dialects.postgresql import JSONB
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
    CheckConstraint("status IN ('pending', 'published', 'dead')", name="status"),
    CheckConstraint("attempts >= 0", name="attempts_non_negative"),
    CheckConstraint("(status = 'published') = (published_at IS NOT NULL)", name="published_at"),
    Index("outbox_pending_idx", "next_attempt_at", postgresql_where=text("status = 'pending'")),
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


class HandlerRegistry:
    """Maps event types to the handlers that react to them.

    Delivery is **at least once**: a handler can run again for an event it already
    processed, e.g. when the worker dies after the handler finished but before the
    event was marked as published, or when another handler for the same event
    failed and the event is retried. Every handler must therefore be idempotent:
    record what it did under the event id (a unique ``source_event_id`` column is
    the usual way) and do nothing if that record already exists. Where this is
    impossible, such as for a plain notification e-mail, a rare duplicate must be
    acceptable.
    """

    def __init__(self) -> None:
        self._handlers: defaultdict[str, list[Handler]] = defaultdict(list)

    def register[E: DomainEvent](
        self, event_class: type[E], handler: Callable[[E], Awaitable[None]]
    ) -> None:
        """Run ``handler`` for every event of ``event_class``."""

        async def typed_handler(event: DomainEvent) -> None:
            if not isinstance(event, event_class):
                msg = f"expected {event_class.__name__}, got {type(event).__name__}"
                raise TypeError(msg)
            await handler(event)

        self._handlers[event_class.event_type].append(typed_handler)

    def handlers_for(self, event_type: str) -> Sequence[Handler]:
        """The handlers registered for ``event_type``, in registration order."""
        return tuple(self._handlers.get(event_type, ()))


class OutboxDispatcher:
    """Delivers outbox events to their handlers (runs in the worker process).

    Rows are claimed with ``FOR UPDATE SKIP LOCKED`` inside one transaction, so any
    number of dispatchers can run side by side without processing an event twice
    concurrently. Handlers run while the rows are locked, then the outcome is stored
    in the same transaction. The dispatcher sleeps until ``NOTIFY mb_outbox`` arrives
    or the poll interval passes; polling also picks up retries whose time has come.
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
    ) -> None:
        self._engine = engine
        self._listen_dsn = listen_dsn
        self._events = events
        self._handlers = handlers
        self._poll_seconds = poll_seconds
        self._max_attempts = max_attempts
        self._batch_size = batch_size
        self._wakeup = asyncio.Event()
        self._listener: asyncpg.Connection | None = None

    async def run(self, stop: asyncio.Event) -> None:
        """Dispatch until ``stop`` is set; the batch in progress is finished first."""
        _logger.info("outbox.dispatcher.started")
        try:
            while not stop.is_set():
                await self._ensure_listener()
                self._wakeup.clear()
                try:
                    processed = await self.dispatch_batch()
                except _DATABASE_UNAVAILABLE as exc:
                    _logger.warning("outbox.dispatch.database_error", error=str(exc))
                    processed = 0
                if processed < self._batch_size:
                    await self._sleep(stop)
        finally:
            await self._close_listener()
            _logger.info("outbox.dispatcher.stopped")

    async def dispatch_batch(self) -> int:
        """Claim and process up to ``batch_size`` due events; return how many."""
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
                await self._process(connection, row)
        return len(rows)

    async def _process(self, connection: AsyncConnection, row: Row[Any]) -> None:
        log: structlog.stdlib.BoundLogger = _logger.bind(
            event_id=str(row.id), event_type=row.event_type
        )
        try:
            event = self._events.deserialize(
                row.event_type,
                event_id=row.id,
                aggregate_id=row.aggregate_id,
                occurred_at=row.occurred_at,
                payload=row.payload,
            )
            for handler in self._handlers.handlers_for(row.event_type):
                await handler(event)
        except Exception as exc:
            await self._record_failure(connection, row, exc, log)
            return

        await connection.execute(
            update(outbox_table)
            .where(outbox_table.c.id == row.id)
            .values(status=OutboxStatus.PUBLISHED, published_at=func.now(), last_error=None)
        )
        if event.audience:
            notification = RealtimeEvent.from_domain_event(event).to_notification()
            await connection.execute(select(func.pg_notify(EVENTS_CHANNEL, notification)))
        log.info("outbox.event.published", attempts=row.attempts)

    async def _record_failure(
        self,
        connection: AsyncConnection,
        row: Row[Any],
        exc: Exception,
        log: structlog.stdlib.BoundLogger,
    ) -> None:
        attempts = row.attempts + 1
        error = f"{type(exc).__name__}: {exc}"[:LAST_ERROR_MAX_LENGTH]
        values: dict[str, Any] = {"attempts": attempts, "last_error": error}
        if attempts >= self._max_attempts:
            values["status"] = OutboxStatus.DEAD
            log.error("outbox.event.dead", attempts=attempts, exc_info=exc)
        else:
            delay = retry_delay(attempts)
            values["next_attempt_at"] = func.now() + delay
            log.warning(
                "outbox.event.retry_scheduled",
                attempts=attempts,
                retry_in_seconds=delay.total_seconds(),
                exc_info=exc,
            )
        await connection.execute(
            update(outbox_table).where(outbox_table.c.id == row.id).values(**values)
        )

    async def _sleep(self, stop: asyncio.Event) -> None:
        waiters = {
            asyncio.ensure_future(self._wakeup.wait()),
            asyncio.ensure_future(stop.wait()),
        }
        try:
            await asyncio.wait(
                waiters, timeout=self._poll_seconds, return_when=asyncio.FIRST_COMPLETED
            )
        finally:
            for waiter in waiters:
                waiter.cancel()

    async def _ensure_listener(self) -> None:
        if self._listener is not None and not self._listener.is_closed():
            return
        try:
            listener = await asyncpg.connect(self._listen_dsn)
            await listener.add_listener(OUTBOX_CHANNEL, self._on_notify)
        except _DATABASE_UNAVAILABLE as exc:
            # Polling keeps the outbox moving; the next loop retries the LISTEN.
            _logger.warning("outbox.listener.unavailable", error=str(exc))
            self._listener = None
            return
        self._listener = listener

    async def _close_listener(self) -> None:
        if self._listener is not None:
            with contextlib.suppress(*_DATABASE_UNAVAILABLE):
                await self._listener.close(timeout=5)
            self._listener = None

    def _on_notify(self, connection: object, pid: int, channel: str, payload: object) -> None:
        self._wakeup.set()
