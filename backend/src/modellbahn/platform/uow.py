"""Unit of work: one database transaction plus the domain events it produced."""

from collections.abc import Collection, Mapping
from datetime import datetime
from types import TracebackType
from typing import Final, Self
from uuid import UUID

from sqlalchemy import func, insert, literal, select, update
from sqlalchemy.dialects.postgresql import JSONB, array
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm.exc import StaleDataError

from modellbahn.platform.events import DomainEvent, EventRegistry, event_registry
from modellbahn.platform.outbox import OUTBOX_CHANNEL, outbox_record, outbox_table

_UNIQUE_VIOLATION: Final = "23505"
_FOREIGN_KEY_VIOLATION: Final = "23503"


class UniqueViolationError(Exception):
    """A UNIQUE constraint rejected the changes (e.g. a concurrent duplicate insert)."""

    def __init__(self, constraint: str | None) -> None:
        super().__init__(f"unique constraint violated: {constraint}")
        self.constraint = constraint


class ForeignKeyViolationError(Exception):
    """A FOREIGN KEY constraint rejected the changes, e.g. deleting a row still referred to.

    Across module boundaries this is how the database answers "still in use": a
    module cannot see who refers to its rows, but the ``RESTRICT`` keys can.
    """

    def __init__(self, constraint: str | None) -> None:
        super().__init__(f"foreign key constraint violated: {constraint}")
        self.constraint = constraint


class ConcurrentUpdateError(Exception):
    """Someone else changed a versioned row between our read and our write."""


class UnitOfWork:
    """Wraps one transaction; use as ``async with uow: ...; await uow.commit()``.

    Domain events passed to :meth:`publish` are written to ``platform.outbox`` by
    :meth:`commit` in the same transaction as the state change, followed by
    ``pg_notify('mb_outbox', '')`` which wakes the worker once the transaction
    commits. Leaving the block without committing rolls everything back,
    including the events. Repositories never commit on their own.

    Modules subclass this to attach their repositories in :meth:`_attach`.
    """

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        events: EventRegistry = event_registry,
    ) -> None:
        self._session_factory = session_factory
        self._events = events
        self._session: AsyncSession | None = None
        self._pending: list[DomainEvent] = []

    @property
    def session(self) -> AsyncSession:
        """The SQLAlchemy session of the open transaction (for repositories and facades)."""
        if self._session is None:
            msg = "the unit of work is not active; use 'async with'"
            raise RuntimeError(msg)
        return self._session

    async def __aenter__(self) -> Self:
        if self._session is not None:
            msg = "a unit of work cannot be entered twice"
            raise RuntimeError(msg)
        self._session = self._session_factory()
        self._pending = []
        self._attach(self._session)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        session = self.session
        try:
            # close() rolls back whatever was not committed, like rollback() would, but
            # leaves loaded aggregates readable (detached, not expired) for the caller.
            await session.close()
        finally:
            self._session = None
            self._pending = []

    def _attach(self, session: AsyncSession) -> None:
        """Hook for subclasses: create the repositories bound to ``session``."""

    def publish(self, *events: DomainEvent) -> None:
        """Collect events to be written to the outbox on :meth:`commit`."""
        for event in events:
            if not self._events.is_registered(type(event)):
                msg = f"{type(event).__name__} is not registered as a domain event"
                raise TypeError(msg)
        self._pending.extend(events)

    async def flush(self) -> None:
        """Send pending changes to the database without committing.

        Raises :class:`UniqueViolationError`, :class:`ForeignKeyViolationError` or
        :class:`ConcurrentUpdateError` so callers can react before doing irreversible
        things (like sending mail).
        """
        try:
            await self.session.flush()
        except IntegrityError as exc:
            violation = _constraint_violation(exc)
            if violation is None:
                raise
            raise violation from exc
        except StaleDataError as exc:
            raise ConcurrentUpdateError(str(exc)) from exc

    async def commit(self) -> None:
        """Write the collected events to the outbox and commit, all in one transaction."""
        session = self.session
        await self.flush()
        if self._pending:
            await session.execute(insert(outbox_table), [outbox_record(e) for e in self._pending])
            await session.execute(select(func.pg_notify(OUTBOX_CHANNEL, "")))
        try:
            await session.commit()
        except IntegrityError as exc:
            # Deferred constraints are only checked here, at the end of the transaction.
            violation = _constraint_violation(exc)
            if violation is None:
                raise
            raise violation from exc
        self._pending = []

    async def rollback(self) -> None:
        """Discard the changes and events so far; the unit of work stays usable."""
        await self.session.rollback()
        self._pending = []

    async def count_recent_events(
        self, aggregate_id: UUID, event_types: Collection[str], *, since: datetime
    ) -> int:
        """How many events of ``event_types`` the aggregate produced from ``since`` on.

        Counts every stored event regardless of its delivery status, e.g. to throttle
        requests that each send an e-mail.
        """
        count = await self.session.scalar(
            select(func.count())
            .select_from(outbox_table)
            .where(
                outbox_table.c.aggregate_id == aggregate_id,
                outbox_table.c.event_type.in_(list(event_types)),
                outbox_table.c.occurred_at >= since,
            )
        )
        return count or 0

    async def redact_events(self, aggregate_id: UUID, replacements: Mapping[str, str]) -> None:
        """Overwrite fields in the stored events of an aggregate, e.g. personal data on erasure.

        Only events that carry one of the fields are changed. The outbox keeps
        published events for the realtime replay, so without this a deleted
        customer's name would keep reaching the admin area. Events published in this
        unit of work are written afterwards and are not affected.
        """
        payload = outbox_table.c.payload
        await self.session.execute(
            update(outbox_table)
            .where(
                outbox_table.c.aggregate_id == aggregate_id,
                payload.has_any(array(list(replacements))),
            )
            .values(payload=payload.op("||")(literal(dict(replacements), JSONB)))
        )


def _constraint_violation(
    exc: IntegrityError,
) -> UniqueViolationError | ForeignKeyViolationError | None:
    original = exc.orig
    sqlstate = getattr(original, "sqlstate", None)
    # SQLAlchemy's asyncpg adapter keeps the driver's exception as the cause;
    # that one knows the name of the violated constraint.
    constraint = getattr(getattr(original, "__cause__", None), "constraint_name", None)
    if sqlstate == _UNIQUE_VIOLATION:
        return UniqueViolationError(constraint)
    if sqlstate == _FOREIGN_KEY_VIOLATION:
        return ForeignKeyViolationError(constraint)
    return None
