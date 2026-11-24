"""The printer bridge (ADR 0047): the printers move the plates in the hall by themselves."""

from collections.abc import AsyncIterator
from typing import Any, Final

import pytest
from asgi_lifespan import LifespanManager
from fastapi import FastAPI
from httpx import AsyncClient
from pydantic import SecretStr

from modellbahn.main import create_app
from modellbahn.modules.media.application.services import MediaService
from modellbahn.platform.config import Settings
from tests.api.helpers import assert_problem
from tests.api.test_manufacturing_api import BASE, ok, part, plate, printer

BRIDGE: Final = "/api/v1/webhooks/printer-bridge"
KEY: Final = "werkstatt-schluessel"
AUTH: Final = {"Authorization": f"Bearer {KEY}"}


@pytest.fixture
async def app(settings: Settings, media: MediaService) -> AsyncIterator[FastAPI]:
    app = create_app(settings.model_copy(update={"printer_bridge_token": SecretStr(KEY)}))
    app.state.media_service = media
    async with LifespanManager(app):
        yield app


async def send(client: AsyncClient, *printers: dict[str, Any]) -> list[dict[str, Any]]:
    response = await client.post(BRIDGE, json={"printers": list(printers)}, headers=AUTH)
    assert response.status_code == 200, response.text
    results: list[dict[str, Any]] = response.json()["results"]
    return results


def seen(state: str, task: str = "t-1", file: str = "STW-ALT-DACH-H0 x4.ctb") -> dict[str, Any]:
    return {
        "code": "d01",
        "state": state,
        "task_id": task,
        "slice_file": f"/local/{file}",
        "elapsed_seconds": 600,
        "remaining_seconds": 6600,
    }


async def job(client: AsyncClient, number: int) -> dict[str, Any]:
    jobs = (await ok(client.get(f"{BASE}/print-jobs")))["items"]
    return next(j for j in jobs if j["number"] == number)


class TestPrinterBridge:
    async def test_a_print_runs_from_start_to_post_processing(
        self, staff_client: AsyncClient, make_client: Any
    ) -> None:
        await printer(staff_client)
        await part(staff_client)
        async with make_client(csrf=False) as bridge:
            (started,) = await send(bridge, seen("printing"))
            assert started["outcome"] == "started"
            again = await send(bridge, seen("printing"))
            assert again[0] == {**started, "outcome": "printing"}
            plate_now = await job(staff_client, started["job_number"])
            assert plate_now["status"] == "printing"
            assert plate_now["planned_minutes"] == 120
            assert plate_now["lines"][0]["quantity"] == 4
            assert "STW-ALT-DACH-H0 x4.ctb" in plate_now["note"]

            (printed,) = await send(bridge, seen("finished"))
            assert printed["outcome"] == "printed"
            assert (await job(staff_client, started["job_number"]))["status"] == "post_processing"
            # The printer still shows the finished print: it is booked once.
            assert (await send(bridge, seen("finished")))[0]["outcome"] == "nothing"
            assert (await send(bridge, seen("printing")))[0]["outcome"] == "already_booked"

    async def test_a_waiting_plate_with_the_part_starts(
        self, staff_client: AsyncClient, make_client: Any
    ) -> None:
        printer_id = await printer(staff_client)
        other = await part(staff_client, "STW-ALT-RAD-H0")
        roof = await part(staff_client)
        first = await plate(staff_client, printer_id, (other, 2))
        second = await plate(staff_client, printer_id, (roof, 4))
        async with make_client(csrf=False) as bridge:
            (result,) = await send(bridge, seen("printing", file="stw_alt_dach_h0.ctb"))
            assert result["job_number"] == second["number"]
            (stopped,) = await send(bridge, {**seen("stopped"), "error": "Folie gerissen"})
            assert stopped["outcome"] == "failed"
            failed = await job(staff_client, second["number"])
            assert failed["status"] == "failed"
            assert failed["failure_reason"] == "Am Drucker abgebrochen: Folie gerissen"
            # A file naming no part takes the next waiting plate.
            (next_one,) = await send(bridge, seen("printing", task="t-2", file="test.ctb"))
            assert next_one["job_number"] == first["number"]

    async def test_without_plate_or_part_nothing_is_booked(
        self, staff_client: AsyncClient, make_client: Any
    ) -> None:
        await printer(staff_client)
        async with make_client(csrf=False) as bridge:
            results = await send(
                bridge, seen("printing", file="probe.ctb"), {**seen("printing"), "code": "D09"}
            )
            assert [r["outcome"] for r in results] == ["unmatched", "unknown_printer"]

    async def test_a_new_print_closes_one_that_ended_unseen(
        self, staff_client: AsyncClient, make_client: Any
    ) -> None:
        await printer(staff_client)
        await part(staff_client)
        async with make_client(csrf=False) as bridge:
            (first,) = await send(bridge, seen("printing"))
            (second,) = await send(bridge, seen("printing", task="t-2"))
            assert second["outcome"] == "started"
            assert (await job(staff_client, first["job_number"]))["status"] == "post_processing"

    async def test_the_key_is_required(self, make_client: Any) -> None:
        async with make_client(csrf=False) as bridge:
            body: dict[str, list[Any]] = {"printers": []}
            assert_problem(await bridge.post(BRIDGE, json=body), 401, "not_authenticated")
            wrong = {"Authorization": "Bearer falsch"}
            assert_problem(
                await bridge.post(BRIDGE, json=body, headers=wrong), 401, "not_authenticated"
            )


async def test_without_a_key_the_bridge_is_off(
    app: FastAPI, settings: Settings, client: AsyncClient
) -> None:
    app.state.settings = settings
    response = await client.post(BRIDGE, json={"printers": []}, headers=AUTH)
    assert response.status_code == 404
