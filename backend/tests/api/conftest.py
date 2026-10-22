"""API tests: the real app (with lifespan) over httpx' ASGI transport."""

from collections.abc import AsyncIterator
from contextlib import AbstractAsyncContextManager
from datetime import UTC, datetime
from typing import Any

import pytest
from asgi_lifespan import LifespanManager
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from modellbahn.main import create_app
from modellbahn.modules.identity.application.services import IdentityService
from modellbahn.modules.identity.domain.model import StaffRole
from modellbahn.platform.clock import FixedClock
from modellbahn.platform.config import Settings
from modellbahn.platform.mail import InMemoryMailer
from tests.api.helpers import (
    ADMIN,
    PASSWORD,
    STAFF_EMAIL,
    STORE,
    ClientFactory,
    register,
)
from tests.conftest import PUBLIC_BASE_URL, Deliver
from tests.support import CSRF_HEADERS, token_from


@pytest.fixture(autouse=True)
def _clean(clean_database: None) -> None:
    """Every API test starts with empty tables."""


@pytest.fixture
def clock() -> FixedClock:
    # The app runs on the system clock; tokens issued by the test's handlers must match it.
    return FixedClock(datetime.now(UTC))


@pytest.fixture
async def app(settings: Settings) -> AsyncIterator[FastAPI]:
    app = create_app(settings)
    async with LifespanManager(app):
        yield app


@pytest.fixture
def make_client(app: FastAPI) -> ClientFactory:
    """A new client with its own cookie jar; sends the CSRF header unless told otherwise."""

    def make(*, csrf: bool = True) -> AbstractAsyncContextManager[AsyncClient]:
        return AsyncClient(
            transport=ASGITransport(app=app),
            base_url=PUBLIC_BASE_URL,
            headers=CSRF_HEADERS if csrf else {},
        )

    return make


@pytest.fixture
async def client(make_client: ClientFactory) -> AsyncIterator[AsyncClient]:
    async with make_client() as client:
        yield client


@pytest.fixture
async def customer(client: AsyncClient, deliver: Deliver, mailer: InMemoryMailer) -> dict[str, Any]:
    """Register and verify the test customer; ``client`` is logged in afterwards."""
    assert (await register(client)).status_code == 202
    await deliver()
    response = await client.post(
        f"{STORE}/email-verification",
        json={"token": token_from(mailer.sent[-1]), "password": PASSWORD},
    )
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


@pytest.fixture
async def staff_client(
    make_client: ClientFactory, identity: IdentityService
) -> AsyncIterator[AsyncClient]:
    """A client logged in to the admin area as owner."""
    await identity.create_staff(
        email=STAFF_EMAIL, display_name="Chefin", role=StaffRole.OWNER, password=PASSWORD
    )
    async with make_client() as client:
        response = await client.post(
            f"{ADMIN}/session", json={"email": STAFF_EMAIL, "password": PASSWORD}
        )
        assert response.status_code == 200, response.text
        yield client
