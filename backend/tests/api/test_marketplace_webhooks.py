"""eBay's calls over HTTP: the check of the endpoint and the notifications of closed accounts.

eBay sends no cookie and no CSRF header; its signature is the proof.
"""

import hashlib
import json
from collections.abc import AsyncIterator
from uuid import uuid4

import pytest
from asgi_lifespan import LifespanManager
from fastapi import FastAPI
from httpx import AsyncClient
from pydantic import SecretStr

from modellbahn.main import create_app
from modellbahn.modules.marketplace.infrastructure.builtin import (
    TEST_BUYER_NAME,
    sign_test_notification,
)
from modellbahn.modules.media.application.services import MediaService
from modellbahn.platform.config import MarketplaceMode, Settings
from tests.api.helpers import ClientFactory
from tests.conftest import PUBLIC_BASE_URL

ENDPOINT = "/api/v1/webhooks/ebay/account-deletion"
TOKEN = "stellwerk_pruefung-0123456789abcdefABCDEF"


@pytest.fixture
def ebay_settings(settings: Settings) -> Settings:
    """The test marketplace, with the verification token entered at eBay."""
    return settings.model_copy(
        update={
            "ebay_mode": MarketplaceMode.TEST,
            "ebay_verification_token": SecretStr(TOKEN),
        }
    )


@pytest.fixture
async def app(ebay_settings: Settings, media: MediaService) -> AsyncIterator[FastAPI]:
    app = create_app(ebay_settings)
    app.state.media_service = media
    async with LifespanManager(app):
        yield app


def notification(username: str) -> bytes:
    return json.dumps(
        {
            "metadata": {"topic": "MARKETPLACE_ACCOUNT_DELETION", "schemaVersion": "1.0"},
            "notification": {
                "notificationId": str(uuid4()),
                "eventDate": "2026-10-29T12:00:00.000Z",
                "publishDate": "2026-10-29T12:00:00.100Z",
                "publishAttemptCount": 1,
                "data": {"username": username, "userId": "a1B2c3D4e5F", "eiasToken": ""},
            },
        },
        separators=(",", ":"),
    ).encode()


class TestEndpointCheck:
    async def test_ebay_gets_the_hash_it_expects(self, make_client: ClientFactory) -> None:
        async with make_client(csrf=False) as ebay:
            response = await ebay.get(ENDPOINT, params={"challenge_code": "a8628072-3d33"})

        assert response.status_code == 200
        assert response.headers["content-type"] == "application/json"
        expected = hashlib.sha256(
            f"a8628072-3d33{TOKEN}{PUBLIC_BASE_URL}{ENDPOINT}".encode()
        ).hexdigest()
        assert response.json() == {"challengeResponse": expected}

    async def test_without_a_challenge_code_there_is_nothing_to_answer(
        self, client: AsyncClient
    ) -> None:
        response = await client.get(ENDPOINT)

        assert response.status_code == 422


class TestNotifications:
    async def test_a_signed_notification_needs_no_csrf_header(
        self, make_client: ClientFactory
    ) -> None:
        body = notification("fremder_nutzer")

        async with make_client(csrf=False) as ebay:
            response = await ebay.post(
                ENDPOINT,
                content=body,
                headers={
                    "Content-Type": "application/json",
                    "X-EBAY-SIGNATURE": sign_test_notification(body),
                },
            )

        assert response.status_code == 204

    async def test_a_forged_notification_is_refused(self, make_client: ClientFactory) -> None:
        async with make_client(csrf=False) as forger:
            response = await forger.post(
                ENDPOINT,
                content=notification(TEST_BUYER_NAME),
                headers={
                    "Content-Type": "application/json",
                    "X-EBAY-SIGNATURE": sign_test_notification(notification("jemand")),
                },
            )

        assert response.status_code == 412
        assert response.json()["code"] == "signature_invalid"

    async def test_a_body_that_is_no_notification(self, make_client: ClientFactory) -> None:
        async with make_client(csrf=False) as forger:
            response = await forger.post(ENDPOINT, content=b"hallo")

        assert response.status_code == 400
        assert response.json()["code"] == "notification_invalid"

    async def test_other_unsafe_requests_still_need_the_header(
        self, make_client: ClientFactory
    ) -> None:
        async with make_client(csrf=False) as forger:
            response = await forger.post("/api/v1/admin/marketplace/ebay/test-buyer/close-account")

        assert response.status_code == 403
        assert response.json()["code"] == "csrf_header_missing"


class TestStellwerk:
    async def test_the_setup_for_ebays_developer_account(self, staff_client: AsyncClient) -> None:
        response = await staff_client.get("/api/v1/admin/marketplace/ebay/account-deletion")

        assert response.status_code == 200
        assert response.json() == {
            "endpoint": f"{PUBLIC_BASE_URL}{ENDPOINT}",
            "token_set": True,
            "checks_signatures": True,
            "test_buyer_name": TEST_BUYER_NAME,
        }

    async def test_the_test_buyer_closes_their_account(self, staff_client: AsyncClient) -> None:
        response = await staff_client.post(
            "/api/v1/admin/marketplace/ebay/test-buyer/close-account"
        )

        assert response.status_code == 200
        assert response.json() == {"erased_orders": 0}


class TestWithoutToken:
    @pytest.fixture
    def ebay_settings(self, settings: Settings) -> Settings:
        return settings.model_copy(update={"ebay_verification_token": SecretStr("")})

    async def test_ebays_check_finds_no_endpoint(self, client: AsyncClient) -> None:
        response = await client.get(ENDPOINT, params={"challenge_code": "a8628072"})

        assert response.status_code == 404
        assert response.json()["code"] == "deletion_endpoint_not_ready"
