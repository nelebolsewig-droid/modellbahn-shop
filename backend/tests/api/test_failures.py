"""How the API fails: an unreachable database, unexpected errors, and what gets logged."""

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from modellbahn.main import create_app
from modellbahn.modules.identity.infrastructure.repositories import SqlLoginSessionRepository
from modellbahn.platform.config import Environment, Settings
from modellbahn.platform.security import Argon2PasswordHasher
from tests.api.helpers import ADMIN, STORE, assert_problem
from tests.conftest import PUBLIC_BASE_URL
from tests.support import CSRF_HEADERS

SECRET_PASSWORD = "Marker-Passwort-4711"
SECRET_TOKEN = "marker-session-token-0815"
DB_PASSWORD = "Db-Secret-0815"


def json_lines(output: str) -> list[dict[str, Any]]:
    return [json.loads(line) for line in output.splitlines() if line.startswith("{")]


@asynccontextmanager
async def production_api(settings: Settings, **changes: object) -> AsyncIterator[AsyncClient]:
    """A client of a production-mode app, without lifespan (no realtime hub needed).

    Use it inside the test itself: creating the app configures logging, and capsys only
    captures what is written to the stream that is current during the test.
    """
    production = {
        "environment": Environment.PRODUCTION,
        "s3_access_key_id": "GK0123456789abcdef01234567",
        **changes,
    }
    app = create_app(settings.model_copy(update=production))
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url=PUBLIC_BASE_URL, headers=CSRF_HEADERS
    ) as client:
        yield client


def staff_cookie(token: str) -> dict[str, str]:
    return {"cookie": f"mb_admin={token}"}


async def test_an_unreachable_database_answers_503(
    settings: Settings, capsys: pytest.CaptureFixture[str]
) -> None:
    unreachable = f"postgresql+asyncpg://shop:{DB_PASSWORD}@127.0.0.1:1/shop"
    async with production_api(settings, database_url=unreachable) as client:
        login = await client.post(
            f"{STORE}/session", json={"email": "kunde@example.com", "password": SECRET_PASSWORD}
        )
        me = await client.get(f"{ADMIN}/me", headers=staff_cookie(SECRET_TOKEN))
        events = await client.get("/api/v1/admin/events", headers=staff_cookie(SECRET_TOKEN))
        ready = await client.get("/readyz")

    for response in (login, me, events, ready):
        assert_problem(response, 503, "database_unavailable")
    assert login.headers["retry-after"] == "5"

    output = capsys.readouterr().err
    lines = [line for line in json_lines(output) if line["event"] == "request.database_unavailable"]
    assert len(lines) == 3
    assert lines[0]["level"] == "warning"
    assert "ConnectionRefusedError" in lines[0]["error"]
    # An outage is not a bug: no traceback, and nothing secret in the log.
    assert "exception" not in output
    for secret in (SECRET_PASSWORD, SECRET_TOKEN, DB_PASSWORD):
        assert secret not in output


async def test_unexpected_errors_leave_secrets_out_of_the_log(
    settings: Settings, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    async def broken(*args: object, **kwargs: object) -> None:
        raise RuntimeError("hasher exploded")

    # Both run with the secret in a local variable of every frame above them.
    monkeypatch.setattr(Argon2PasswordHasher, "dummy_verify", broken)
    monkeypatch.setattr(SqlLoginSessionRepository, "get", broken)

    async with production_api(settings) as client:
        login = await client.post(
            f"{STORE}/session", json={"email": "niemand@example.com", "password": SECRET_PASSWORD}
        )
        me = await client.get(f"{ADMIN}/me", headers=staff_cookie(SECRET_TOKEN))

    body = assert_problem(login, 500, "internal_error")
    assert body["detail"] == "An unexpected error occurred."
    assert_problem(me, 500, "internal_error")
    output = capsys.readouterr().err
    failures = [line for line in json_lines(output) if line["event"] == "request.failed"]
    assert [line["path"] for line in failures] == [f"{STORE}/session", f"{ADMIN}/me"]
    (exception,) = failures[0]["exception"]
    assert exception["exc_value"] == "hasher exploded"
    assert all("locals" not in frame for frame in exception["frames"])
    assert SECRET_PASSWORD not in output
    assert SECRET_TOKEN not in output
