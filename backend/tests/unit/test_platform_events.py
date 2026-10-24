"""Domain event base class, registry and (de)serialisation."""

from dataclasses import dataclass
from datetime import datetime
from typing import ClassVar
from uuid import UUID, uuid4

import pytest

from modellbahn.platform.events import DomainEvent, EventRegistry, UnknownEventTypeError
from modellbahn.platform.ids import new_id
from tests.support import NOW, Colour, SampleHappened, sample


def test_new_id_is_a_time_ordered_uuid7() -> None:
    first, second = new_id(), new_id()
    assert type(first) is UUID
    assert first.version == 7
    assert first < second


def test_payload_round_trip() -> None:
    registry = EventRegistry()
    registry.register(SampleHappened)
    event = sample()

    payload = event.payload()
    assert payload["colour"] == "red"
    assert payload["other"] == str(event.other)
    assert "event_id" not in payload

    restored = registry.deserialize(
        SampleHappened.event_type,
        event_id=event.event_id,
        aggregate_id=event.aggregate_id,
        occurred_at=event.occurred_at,
        payload=payload,
    )
    assert restored == event


def test_default_public_payload_is_empty() -> None:
    assert sample().public_payload() == {}


def test_registry_lookups() -> None:
    registry = EventRegistry()
    registry.register(SampleHappened)
    assert registry.resolve("test.sample.happened") is SampleHappened
    assert registry.is_registered(SampleHappened)
    assert registry.event_types_for("staff") == ["test.sample.happened"]
    assert registry.event_types_for("customers") == []
    with pytest.raises(UnknownEventTypeError):
        registry.resolve("test.unknown")


def test_registering_twice_is_idempotent_but_names_are_unique() -> None:
    registry = EventRegistry()
    registry.register(SampleHappened)
    registry.register(SampleHappened)

    @dataclass(frozen=True, kw_only=True)
    class Impostor(DomainEvent):
        event_type: ClassVar[str] = "test.sample.happened"
        aggregate_type: ClassVar[str] = "test.sample"

    with pytest.raises(ValueError, match="already registered"):
        registry.register(Impostor)


def test_rejects_unsupported_payload_types() -> None:
    @dataclass(frozen=True, kw_only=True)
    class WithList(DomainEvent):
        event_type: ClassVar[str] = "test.with_list"
        aggregate_type: ClassVar[str] = "test"
        items: list[str]

    with pytest.raises(TypeError, match="unsupported payload type"):
        EventRegistry().register(WithList)


def test_rejects_classes_without_type_names_or_dataclass() -> None:
    @dataclass(frozen=True, kw_only=True)
    class Nameless(DomainEvent):
        pass

    class NotADataclass(DomainEvent):
        event_type: ClassVar[str] = "test.plain"
        aggregate_type: ClassVar[str] = "test"

    with pytest.raises(TypeError, match="event_type"):
        EventRegistry().register(Nameless)
    with pytest.raises(TypeError, match="dataclass"):
        EventRegistry().register(NotADataclass)


def test_occurred_at_must_be_timezone_aware() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        SampleHappened(
            aggregate_id=uuid4(),
            occurred_at=datetime(2026, 1, 1),  # noqa: DTZ001
            name="x",
            count=1,
            ratio=1.0,
            flag=False,
            other=uuid4(),
            when=NOW,
            colour=Colour.RED,
        )
