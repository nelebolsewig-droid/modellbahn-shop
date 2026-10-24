"""Domain events: base class, registry and JSON (de)serialisation.

This module is pure Python on purpose: the domain layers of the modules import it,
and they must not depend on any framework.
"""

import dataclasses
import types
import typing
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, ClassVar, Final
from uuid import UUID

from modellbahn.platform.ids import new_id

type JsonValue = str | int | float | bool | list[JsonValue] | dict[str, JsonValue] | None
type JsonObject = dict[str, JsonValue]

ENVELOPE_FIELDS: Final = frozenset({"event_id", "occurred_at", "aggregate_id"})
_SCALAR_TYPES: Final = (str, int, float, bool)


@dataclass(frozen=True, kw_only=True)
class DomainEvent:
    """Something that happened in the domain, recorded in the outbox.

    Subclasses are frozen, keyword-only dataclasses that set the class variables
    and are registered with :func:`domain_event`. Their own fields form the
    payload and may only use JSON-friendly types: ``str``, ``int``, ``float``,
    ``bool``, ``UUID``, ``datetime``, ``StrEnum`` (each optionally ``| None``).

    Payloads are stored for a long time, so they must never contain secrets
    (tokens, password hashes) and should avoid personal data that the handler can
    load itself (e.g. the e-mail address of an account).
    """

    event_type: ClassVar[str]
    """Stable name, ``<module>.<aggregate>.<what happened>``."""
    aggregate_type: ClassVar[str]
    audience: ClassVar[frozenset[str]] = frozenset()
    """Realtime audiences (e.g. ``{"staff"}``) that receive the event via SSE."""

    aggregate_id: UUID
    occurred_at: datetime
    event_id: UUID = field(default_factory=new_id)

    def __post_init__(self) -> None:
        if self.occurred_at.tzinfo is None:
            msg = "occurred_at must be timezone-aware"
            raise ValueError(msg)

    def payload(self) -> JsonObject:
        """The event's own fields (everything except the envelope) as JSON."""
        return {
            f.name: _encode(getattr(self, f.name))
            for f in dataclasses.fields(self)
            if f.name not in ENVELOPE_FIELDS
        }

    def public_payload(self) -> JsonObject:
        """What may be pushed to realtime subscribers. Empty unless overridden."""
        return {}


class UnknownEventTypeError(LookupError):
    """Raised when an event type string has no registered class."""


class EventRegistry:
    """Two-way mapping between event type strings and event classes."""

    def __init__(self) -> None:
        self._classes: dict[str, type[DomainEvent]] = {}

    def register[E: type[DomainEvent]](self, event_class: E) -> E:
        """Register ``event_class`` (usable as a class decorator)."""
        # DomainEvent is frozen, so a dataclass subclass is necessarily frozen too.
        if "__dataclass_fields__" not in vars(event_class):
            msg = (
                f"{event_class.__name__} must be decorated with "
                "@dataclass(frozen=True, kw_only=True)"
            )
            raise TypeError(msg)
        for name in ("event_type", "aggregate_type"):
            if name not in vars(event_class):
                msg = f"{event_class.__name__} must define the class variable {name!r}"
                raise TypeError(msg)
        _check_payload_types(event_class)
        existing = self._classes.get(event_class.event_type)
        if existing is not None and existing is not event_class:
            msg = (
                f"event type {event_class.event_type!r} is already registered "
                f"by {existing.__name__}"
            )
            raise ValueError(msg)
        self._classes[event_class.event_type] = event_class
        return event_class

    def is_registered(self, event_class: type[DomainEvent]) -> bool:
        """True if ``event_class`` itself is registered under its event type."""
        return self._classes.get(event_class.event_type) is event_class

    def resolve(self, event_type: str) -> type[DomainEvent]:
        """The class registered for ``event_type``; :class:`UnknownEventTypeError` otherwise."""
        try:
            return self._classes[event_type]
        except KeyError:
            raise UnknownEventTypeError(event_type) from None

    def event_types(self) -> list[str]:
        """Every registered event type."""
        return sorted(self._classes)

    def event_types_for(self, audience: str) -> list[str]:
        """All registered event types that are delivered to ``audience``."""
        return sorted(name for name, cls in self._classes.items() if audience in cls.audience)

    def deserialize(
        self,
        event_type: str,
        *,
        event_id: UUID,
        aggregate_id: UUID,
        occurred_at: datetime,
        payload: Mapping[str, Any],
    ) -> DomainEvent:
        """Rebuild an event from its outbox representation."""
        event_class = self.resolve(event_type)
        values = {
            name: _decode(payload[name], hint)
            for name, hint in _payload_fields(event_class)
            if name in payload
        }
        return event_class(
            event_id=event_id, aggregate_id=aggregate_id, occurred_at=occurred_at, **values
        )


event_registry = EventRegistry()
"""The process-wide registry that the outbox and the realtime hub use."""


def domain_event[E: type[DomainEvent]](event_class: E) -> E:
    """Class decorator that registers an event class with :data:`event_registry`."""
    return event_registry.register(event_class)


def _payload_fields(event_class: type[DomainEvent]) -> Iterable[tuple[str, Any]]:
    hints = typing.get_type_hints(event_class)
    for f in dataclasses.fields(event_class):
        if f.name not in ENVELOPE_FIELDS:
            yield f.name, hints[f.name]


def _check_payload_types(event_class: type[DomainEvent]) -> None:
    for name, hint in _payload_fields(event_class):
        args = _non_none_args(hint)
        if len(args) != 1 or not _is_supported(args[0]):
            msg = f"{event_class.__name__}.{name}: unsupported payload type {hint!r}"
            raise TypeError(msg)


def _non_none_args(hint: Any) -> tuple[Any, ...]:
    if isinstance(hint, types.UnionType) or typing.get_origin(hint) is typing.Union:
        return tuple(arg for arg in typing.get_args(hint) if arg is not type(None))
    return (hint,)


def _is_supported(hint: Any) -> bool:
    return isinstance(hint, type) and issubclass(hint, (*_SCALAR_TYPES, UUID, datetime, Enum))


def _encode(value: object) -> JsonValue:
    match value:
        case None:
            return None
        case Enum():
            return _encode(value.value)
        case UUID():
            return str(value)
        case datetime():
            return value.isoformat()
        case str() | int() | float() | bool():
            return value
    msg = f"cannot encode {type(value).__name__} in an event payload"
    raise TypeError(msg)


def _decode(value: Any, hint: Any) -> Any:
    if value is None:
        return None
    (target,) = _non_none_args(hint)
    if issubclass(target, datetime):
        return datetime.fromisoformat(value)
    if issubclass(target, (UUID, Enum)):
        return target(value)
    return value
