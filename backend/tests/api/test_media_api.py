"""The media API of the admin area: upload tickets, completion, state, deletion."""

import json
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from modellbahn.platform.realtime import RealtimeHub
from tests.api.helpers import MEDIA, assert_problem
from tests.conftest import Deliver
from tests.media_support import InMemoryMediaStorage, photo, sha256
from tests.support import EventStream, eventually

EVENTS = "/api/v1/admin/events"


def announcement(data: bytes, **changes: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "filename": "stellwerk.jpg",
        "mime_type": "image/jpeg",
        "size_bytes": len(data),
        "sha256": sha256(data),
    }
    body.update(changes)
    return body


async def test_upload_to_ready(
    staff_client: AsyncClient, media_storage: InMemoryMediaStorage, deliver: Deliver
) -> None:
    data = photo(1000, 700)
    response = await staff_client.post(f"{MEDIA}/uploads", json=announcement(data))
    assert response.status_code == 200, response.text
    ticket = response.json()
    asset_id = ticket["asset"]["id"]
    assert ticket["asset"]["status"] == "pending_upload"
    assert ticket["upload"]["method"] == "PUT"
    assert ticket["upload"]["headers"] == {"Content-Type": "image/jpeg"}
    assert ticket["upload"]["url"].startswith("https://storage.test/")

    media_storage.upload(UUID(asset_id), data)
    completed = await staff_client.post(f"{MEDIA}/{asset_id}/complete")
    assert completed.status_code == 200, completed.text
    assert completed.json()["status"] == "uploaded"

    await deliver()
    asset = (await staff_client.get(f"{MEDIA}/{asset_id}")).json()
    assert asset["status"] == "ready"
    assert asset["image"]["width"] == 1000
    assert asset["image"]["dominant_color"].startswith("#")
    urls = {r["url"] for r in asset["renditions"]}
    assert all(url.startswith(f"/medien/{asset_id}/") for url in urls)
    assert {r["name"] for r in asset["renditions"]} == {"thumb", "sm", "md"}

    known = await staff_client.post(f"{MEDIA}/uploads", json=announcement(data))
    assert known.json()["asset"]["id"] == asset_id
    assert known.json()["upload"] is None


async def test_ready_reaches_the_admin_area_live(
    app: FastAPI,
    staff_client: AsyncClient,
    media_storage: InMemoryMediaStorage,
    deliver: Deliver,
) -> None:
    data = photo(400, 300)
    ticket = (await staff_client.post(f"{MEDIA}/uploads", json=announcement(data))).json()
    asset_id = ticket["asset"]["id"]
    media_storage.upload(UUID(asset_id), data)
    await staff_client.post(f"{MEDIA}/{asset_id}/complete")
    hub: RealtimeHub = app.state.realtime_hub
    headers = {"cookie": f"mb_admin={staff_client.cookies['mb_admin']}"}
    async with EventStream(app, EVENTS, headers) as stream:

        async def subscribed() -> bool | None:
            return True if hub.subscriber_count >= 1 else None

        await eventually(subscribed)
        await deliver()
        await deliver()
        message = await stream.next_event()
    assert message.event == "media.asset.ready"
    assert message.data is not None
    assert json.loads(message.data)["data"] == {"asset_id": asset_id}


@pytest.mark.parametrize(
    ("changes", "field", "code"),
    [
        ({"mime_type": "image/gif"}, "mime_type", "unsupported_type"),
        ({"size_bytes": 60 * 1024 * 1024}, "size_bytes", "too_large"),
        ({"filename": "   "}, "filename", "invalid_filename"),
    ],
)
async def test_refused_announcements_name_the_field(
    staff_client: AsyncClient, changes: dict[str, Any], field: str, code: str
) -> None:
    response = await staff_client.post(f"{MEDIA}/uploads", json=announcement(b"x", **changes))
    body = assert_problem(response, 422, "validation_failed")
    assert body["errors"] == [
        {"field": field, "code": code, "message": body["errors"][0]["message"]}
    ]


async def test_checksum_must_be_sha256(staff_client: AsyncClient) -> None:
    response = await staff_client.post(f"{MEDIA}/uploads", json=announcement(b"x", sha256="abc"))
    assert_problem(response, 422, "validation_failed")


async def test_completion_needs_the_file(
    staff_client: AsyncClient, media_storage: InMemoryMediaStorage
) -> None:
    data = photo()
    ticket = (await staff_client.post(f"{MEDIA}/uploads", json=announcement(data))).json()
    asset_id = ticket["asset"]["id"]
    assert_problem(await staff_client.post(f"{MEDIA}/{asset_id}/complete"), 409, "upload_missing")
    media_storage.upload(UUID(asset_id), data + b"!")
    assert_problem(
        await staff_client.post(f"{MEDIA}/{asset_id}/complete"), 409, "upload_size_mismatch"
    )
    assert_problem(
        await staff_client.post(f"{MEDIA}/{asset_id}/reprocess"), 409, "invalid_asset_state"
    )
    assert_problem(await staff_client.get(f"{MEDIA}/{uuid4()}"), 404, "asset_not_found")


async def test_delete(staff_client: AsyncClient) -> None:
    ticket = (await staff_client.post(f"{MEDIA}/uploads", json=announcement(photo()))).json()
    asset_id = ticket["asset"]["id"]
    assert (await staff_client.delete(f"{MEDIA}/{asset_id}")).status_code == 204
    assert_problem(await staff_client.delete(f"{MEDIA}/{asset_id}"), 404, "asset_not_found")


async def test_only_back_office_staff(client: AsyncClient, packer_client: AsyncClient) -> None:
    body = announcement(photo())
    assert_problem(await client.post(f"{MEDIA}/uploads", json=body), 401, "not_authenticated")
    assert_problem(
        await packer_client.post(f"{MEDIA}/uploads", json=body), 403, "insufficient_role"
    )
