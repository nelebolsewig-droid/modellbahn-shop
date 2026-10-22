"""The admin event stream (SSE): live delivery and Last-Event-ID replay."""

import json

from fastapi import FastAPI
from httpx import AsyncClient

from modellbahn.platform.realtime import RealtimeHub
from tests.api.helpers import ADMIN, EMAIL, assert_problem, register
from tests.conftest import Deliver
from tests.support import EventStream, SseMessage, eventually

EVENTS = "/api/v1/admin/events"


def staff_headers(staff_client: AsyncClient, **extra: str) -> dict[str, str]:
    return {"cookie": f"mb_admin={staff_client.cookies['mb_admin']}", **extra}


async def subscribed(hub: RealtimeHub, count: int) -> None:
    async def ready() -> bool | None:
        return True if hub.subscriber_count >= count else None

    await eventually(ready)


def data(message: SseMessage) -> dict[str, object]:
    assert message.data is not None
    parsed: dict[str, object] = json.loads(message.data)
    return parsed


async def test_needs_a_staff_session(client: AsyncClient) -> None:
    assert_problem(await client.get(EVENTS), 401, "not_authenticated")


async def test_registration_appears_live(
    app: FastAPI, staff_client: AsyncClient, client: AsyncClient, deliver: Deliver
) -> None:
    hub: RealtimeHub = app.state.realtime_hub
    async with EventStream(app, EVENTS, staff_headers(staff_client)) as stream:
        assert stream.status == 200
        assert stream.response_headers["content-type"].startswith("text/event-stream")
        assert stream.response_headers["cache-control"] == "no-cache"
        await subscribed(hub, 1)

        await register(client, name="Erika Muster")
        await deliver()
        message = await stream.next_event()

    assert message.event == "identity.customer.registered"
    payload = data(message)
    assert message.id == payload["id"]
    assert payload["type"] == "identity.customer.registered"
    assert payload["truncated"] is False
    event_data = payload["data"]
    assert isinstance(event_data, dict)
    assert event_data["display_name"] == "Erika Muster"
    # Customers' e-mail addresses never reach the stream.
    assert EMAIL not in (message.data or "")


async def test_reconnect_replays_what_was_missed(
    app: FastAPI, staff_client: AsyncClient, client: AsyncClient, deliver: Deliver
) -> None:
    hub: RealtimeHub = app.state.realtime_hub
    async with EventStream(app, EVENTS, staff_headers(staff_client)) as stream:
        await subscribed(hub, 1)
        await register(client, email="erste@example.com", name="Erste")
        await deliver()
        first = await stream.next_event()

    # While disconnected, two more customers register (one of them twice).
    await register(client, email="zweite@example.com", name="Zweite")
    await register(client, email="dritte@example.com", name="Dritte")
    await register(client, email="dritte@example.com", name="Nochmal")
    await deliver()

    assert first.id is not None
    headers = staff_headers(staff_client, **{"Last-Event-ID": first.id})
    async with EventStream(app, EVENTS, headers) as stream:
        replayed = [await stream.next_event(), await stream.next_event()]
        await subscribed(hub, 1)
        await register(client, email="vierte@example.com", name="Vierte")
        await deliver()
        live = await stream.next_event()

    names = [data(message)["data"] for message in [*replayed, live]]
    assert [name["display_name"] for name in names if isinstance(name, dict)] == [
        "Zweite",
        "Dritte",
        "Vierte",
    ]


async def test_a_new_event_source_resumes_with_the_query_parameter(
    app: FastAPI, staff_client: AsyncClient, client: AsyncClient, deliver: Deliver
) -> None:
    # A browser that gave up and opens a new EventSource cannot send Last-Event-ID;
    # the frontend passes the last id it saw as a query parameter instead.
    hub: RealtimeHub = app.state.realtime_hub
    async with EventStream(app, EVENTS, staff_headers(staff_client)) as stream:
        await subscribed(hub, 1)
        await register(client, email="erste@example.com", name="Erste")
        await deliver()
        first = await stream.next_event()

    await register(client, email="zweite@example.com", name="Zweite")
    await deliver()

    assert first.id is not None
    path = f"{EVENTS}?last_event_id={first.id}"
    async with EventStream(app, path, staff_headers(staff_client)) as stream:
        replayed = await stream.next_event()

    payload = data(replayed)["data"]
    assert isinstance(payload, dict)
    assert payload["display_name"] == "Zweite"


async def test_logout_ends_an_open_stream(
    app: FastAPI, staff_client: AsyncClient, client: AsyncClient, deliver: Deliver
) -> None:
    hub: RealtimeHub = app.state.realtime_hub
    async with EventStream(app, EVENTS, staff_headers(staff_client)) as stream:
        await subscribed(hub, 1)
        assert (await staff_client.delete(f"{ADMIN}/session")).status_code == 204

        # The next event would reach a client whose session is gone: the stream ends
        # instead of delivering it.
        await register(client, name="Nach der Abmeldung")
        await deliver()
        await stream.wait_closed()
        assert stream.received_events() == []


async def test_invalid_last_event_id_is_ignored(
    app: FastAPI, staff_client: AsyncClient, client: AsyncClient, deliver: Deliver
) -> None:
    await register(client)
    await deliver()
    hub: RealtimeHub = app.state.realtime_hub
    headers = staff_headers(staff_client, **{"Last-Event-ID": "not-a-uuid"})
    async with EventStream(app, EVENTS, headers) as stream:
        await subscribed(hub, 1)
        await register(client, email="neu@example.com", name="Neu")
        await deliver()
        message = await stream.next_event()
    payload = data(message)["data"]
    assert isinstance(payload, dict)
    assert payload["display_name"] == "Neu"
