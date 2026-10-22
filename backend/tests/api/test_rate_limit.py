"""Per-client limit of the login, registration and reset routes: 429 with Retry-After."""

from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from modellbahn.main import create_app
from modellbahn.platform.config import Settings
from tests.api.helpers import ADMIN, EMAIL, PASSWORD, STORE, assert_problem, register
from tests.conftest import PUBLIC_BASE_URL
from tests.support import CSRF_HEADERS

type ClientAt = Callable[[str], AbstractAsyncContextManager[AsyncClient]]

WINDOW_SECONDS = 600


@pytest.fixture
def limited_app(settings: Settings) -> FastAPI:
    # No lifespan: these routes need the database, not the realtime hub.
    return create_app(
        settings.model_copy(
            update={"auth_rate_limit": 3, "auth_rate_window_seconds": WINDOW_SECONDS}
        )
    )


@pytest.fixture
def client_at(limited_app: FastAPI) -> ClientAt:
    """A client whose requests come from the given address."""

    def make(address: str) -> AbstractAsyncContextManager[AsyncClient]:
        return AsyncClient(
            transport=ASGITransport(app=limited_app, client=(address, 40000)),
            base_url=PUBLIC_BASE_URL,
            headers=CSRF_HEADERS,
        )

    return make


@pytest.fixture
async def attacker(client_at: ClientAt) -> AsyncIterator[AsyncClient]:
    async with client_at("203.0.113.7") as client:
        yield client


async def login(client: AsyncClient, email: str = EMAIL) -> int:
    response = await client.post(f"{STORE}/session", json={"email": email, "password": PASSWORD})
    return response.status_code


async def test_requests_beyond_the_limit_get_429_with_retry_after(attacker: AsyncClient) -> None:
    assert [await login(attacker, f"kunde{n}@example.com") for n in range(3)] == [401] * 3

    response = await attacker.post(
        f"{STORE}/session", json={"email": "kunde9@example.com", "password": PASSWORD}
    )

    assert_problem(response, 429, "too_many_requests")
    assert 0 < int(response.headers["retry-after"]) <= WINDOW_SECONDS


async def test_the_routes_share_one_budget_per_client(attacker: AsyncClient) -> None:
    assert (await register(attacker)).status_code == 202
    reset = await attacker.post(f"{STORE}/password-reset", json={"email": EMAIL})
    assert reset.status_code == 202
    assert await login(attacker, "fremd@example.com") == 401

    staff = await attacker.post(f"{ADMIN}/session", json={"email": EMAIL, "password": PASSWORD})

    assert_problem(staff, 429, "too_many_requests")


async def test_other_clients_are_not_affected(attacker: AsyncClient, client_at: ClientAt) -> None:
    for _ in range(4):
        await login(attacker)

    async with client_at("198.51.100.20") as neighbour:
        assert await login(neighbour) == 401


async def test_the_limit_leaves_other_routes_alone(attacker: AsyncClient) -> None:
    for _ in range(4):
        await login(attacker)

    assert (await attacker.get("/healthz")).status_code == 200
    assert_problem(await attacker.get(f"{STORE}/me"), 401, "not_authenticated")
