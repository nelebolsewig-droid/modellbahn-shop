"""eBay's notifications of closed accounts: the endpoint check and the signature.

The signature cases are the test vectors of eBay's own SDK
(github.com/eBay/event-notification-nodejs-sdk, test/test.json): a notification signed
with eBay's key, the same signature on a changed notification, and a foreign signature.
"""

import base64
import json
from datetime import UTC, datetime
from typing import Any, NoReturn

import httpx
import pytest
from pydantic import SecretStr, ValidationError

from modellbahn.modules.marketplace.application.deletions import AccountDeletionService
from modellbahn.modules.marketplace.application.ports import (
    MarketplaceRejectedError,
    MarketplaceUnavailableError,
    NotificationKey,
)
from modellbahn.modules.marketplace.domain.errors import DeletionEndpointNotReadyError
from modellbahn.modules.marketplace.infrastructure.builtin import (
    TEST_NOTIFICATION_KEY_ID,
    public_test_key,
    sign_test_notification,
)
from modellbahn.modules.marketplace.infrastructure.ebay import APPLICATION_SCOPE
from modellbahn.modules.marketplace.infrastructure.notifications import (
    EcdsaNotificationSignatures,
)
from modellbahn.platform.clock import FixedClock
from modellbahn.platform.config import MarketplaceMode, Settings
from tests.unit.test_marketplace_ebay import API, Recorder, gateway

EBAY_KEY_ID = "9936261a-7d7b-4621-a0f1-96ccb428af49"
EBAY_KEY = NotificationKey(
    pem=(
        "-----BEGIN PUBLIC KEY-----MFkwEwYHKoZIzj0CAQYIKoZIzj0DAQcDQgAEZhhxXKtR+TOvtDbgTPCkSof02q"
        "gBB7IsYOyf76ilExJ/upAa/vKIKheOoCyOpcLmi4t0b4uepb7LLjmMr90FUg==-----END PUBLIC KEY-----"
    ),
    algorithm="ECDSA",
    digest="SHA1",
)
EBAY_SIGNATURE = (
    "eyJhbGciOiJlY2RzYSIsImtpZCI6Ijk5MzYyNjFhLTdkN2ItNDYyMS1hMGYxLTk2Y2NiNDI4YWY0OSIsInNpZ25h"
    "dHVyZSI6Ik1FWUNJUUNmeGZJV3V4bVdjSUJRSjljNS9YN2lHREpxczJSQ0dzQkVhQWppbnlycmZBSWhBSVY2d0dj"
    "VGlCdVY1S0pVaWYyaG9reXJMK1E5c3NIa2FkK214Mm5FRTI1dyIsImRpZ2VzdCI6IlNIQTEifQ=="
)
FOREIGN_SIGNATURE = (
    "eyJhbGciOiJlY2RzYSIsImtpZCI6Ijk5MzYyNjFhLTdkN2ItNDYyMS1hMGYxLTk2Y2NiNDI4YWY0OSIsInNpZ25h"
    "dHVyZSI6Ik1FVUNJUUNHY1NubUFrVGZyK1paMlZnMGJXRW9zOGEvdGVCcWk3UGU2OCtoR21MTUNRSWdlRnZrcnRv"
    "KzhkczhSVndJM0dnbjFtTUdDck5NRVpKM1NSbE8yZngveHFJPSIsImRpZ2VzdCI6IlNIQTEifQ=="
)


def ebay_notification(**changes: Any) -> dict[str, Any]:
    notification: dict[str, Any] = {
        "notificationId": (
            "49feeaeb-4982-42d9-a377-9645b8479411_33f7e043-fed8-442b-9d44-791923bd9a6d"
        ),
        "eventDate": "2021-03-19T20:43:59.462Z",
        "publishDate": "2021-03-19T20:43:59.679Z",
        "publishAttemptCount": 1,
        "data": {
            "username": "test_user",
            "userId": "ma8vp1jySJC",
            "eiasToken": "nY+sHZ2PrBmdj6wVnY+sEZ2PrA2dj6wJnY+gAZGEpwmdj6x9nY+seQ==",
        },
    }
    notification.update(changes)
    return {
        "metadata": {
            "topic": "MARKETPLACE_ACCOUNT_DELETION",
            "schemaVersion": "1.0",
            "deprecated": False,
        },
        "notification": notification,
    }


def compact(message: dict[str, Any]) -> bytes:
    """As eBay's SDK serialises a notification (JSON.stringify)."""
    return json.dumps(message, separators=(",", ":")).encode()


class Keys:
    """eBay's Notification API, counting the lookups."""

    def __init__(self, keys: dict[str, NotificationKey]) -> None:
        self.keys = keys
        self.lookups: list[str] = []

    async def notification_key(self, key_id: str) -> NotificationKey:
        self.lookups.append(key_id)
        if key_id not in self.keys:
            raise MarketplaceRejectedError("195001", "no such key")
        return self.keys[key_id]


def header(**fields: str) -> str:
    return base64.b64encode(json.dumps(fields).encode()).decode()


class TestSignature:
    async def test_ebays_signature_is_accepted(self) -> None:
        signatures = EcdsaNotificationSignatures(Keys({EBAY_KEY_ID: EBAY_KEY}))

        assert await signatures.verify(compact(ebay_notification()), EBAY_SIGNATURE)

    async def test_a_body_with_spaces_counts_as_ebay_serialises_it(self) -> None:
        signatures = EcdsaNotificationSignatures(Keys({EBAY_KEY_ID: EBAY_KEY}))

        assert await signatures.verify(
            json.dumps(ebay_notification(), indent=2).encode(), EBAY_SIGNATURE
        )

    async def test_a_changed_notification_is_refused(self) -> None:
        signatures = EcdsaNotificationSignatures(Keys({EBAY_KEY_ID: EBAY_KEY}))
        changed = ebay_notification(publishAttemptCount=1000)

        assert not await signatures.verify(compact(changed), EBAY_SIGNATURE)

    async def test_a_foreign_signature_is_refused(self) -> None:
        signatures = EcdsaNotificationSignatures(Keys({EBAY_KEY_ID: EBAY_KEY}))

        assert not await signatures.verify(compact(ebay_notification()), FOREIGN_SIGNATURE)

    async def test_the_key_is_fetched_once(self) -> None:
        keys = Keys({EBAY_KEY_ID: EBAY_KEY})
        signatures = EcdsaNotificationSignatures(keys)

        await signatures.verify(compact(ebay_notification()), EBAY_SIGNATURE)
        await signatures.verify(compact(ebay_notification()), FOREIGN_SIGNATURE)

        assert keys.lookups == [EBAY_KEY_ID]

    async def test_a_key_ebay_does_not_know_is_refused_and_not_kept(self) -> None:
        keys = Keys({})
        signatures = EcdsaNotificationSignatures(keys)

        assert not await signatures.verify(compact(ebay_notification()), EBAY_SIGNATURE)
        assert not await signatures.verify(compact(ebay_notification()), EBAY_SIGNATURE)
        assert keys.lookups == [EBAY_KEY_ID, EBAY_KEY_ID]

    @pytest.mark.parametrize(
        "signature",
        [
            "",
            "kein-base64!",
            base64.b64encode(b"kein json").decode(),
            header(alg="rsa", kid=EBAY_KEY_ID, signature="AAAA", digest="SHA1"),
            header(alg="ecdsa", kid=EBAY_KEY_ID, signature="AAAA", digest="MD5"),
            header(alg="ecdsa", signature="AAAA", digest="SHA1"),
        ],
    )
    async def test_a_malformed_header_is_refused(self, signature: str) -> None:
        signatures = EcdsaNotificationSignatures(Keys({EBAY_KEY_ID: EBAY_KEY}))

        assert not await signatures.verify(compact(ebay_notification()), signature)

    async def test_the_test_marketplace_signs_as_ebay_does(self) -> None:
        keys = Keys({TEST_NOTIFICATION_KEY_ID: public_test_key()})
        signatures = EcdsaNotificationSignatures(keys)
        body = compact(ebay_notification())

        other = body.replace(b"test_user", b"some_buyer")

        assert await signatures.verify(body, sign_test_notification(body))
        assert not await signatures.verify(other, sign_test_notification(body))


class TestChallenge:
    def service(self, token: str) -> AccountDeletionService:
        def no_database() -> NoReturn:
            msg = "answering eBay's check needs no database"
            raise AssertionError(msg)

        return AccountDeletionService(
            uow_factory=no_database,
            signatures=None,
            verification_token=token,
            endpoint="https://adp-modelle.de/api/v1/webhooks/ebay/account-deletion",
            clock=FixedClock(datetime(2026, 10, 29, tzinfo=UTC)),
        )

    def test_the_answer_is_the_hash_ebay_expects(self) -> None:
        service = self.service("stellwerk_pruefung-0123456789abcdefABCDEF")

        # SHA-256 of challenge code, verification token and endpoint, as eBay's SDK has it.
        assert service.challenge_response("a8628072-3d33-45ee-9004-bee86830a22d") == (
            "ee916b2968504a5e65cf2abe023c40a68e0b013b48f1482f1fe72fb58db7f6c6"
        )

    def test_without_a_token_there_is_no_answer(self) -> None:
        with pytest.raises(DeletionEndpointNotReadyError):
            self.service("").challenge_response("a8628072")


class TestApplicationToken:
    async def test_the_key_comes_with_the_apps_own_token(self) -> None:
        def token(request: httpx.Request) -> httpx.Response:
            form = dict(httpx.QueryParams(request.content.decode()))
            assert form == {"grant_type": "client_credentials", "scope": APPLICATION_SCOPE}
            return httpx.Response(200, json={"access_token": "app-token", "expires_in": 7200})

        def key(request: httpx.Request) -> httpx.Response:
            assert request.headers["Authorization"] == "Bearer app-token"
            return httpx.Response(
                200, json={"key": EBAY_KEY.pem, "algorithm": "ECDSA", "digest": "SHA1"}
            )

        recorder = Recorder(
            {
                ("POST", "/identity/v1/oauth2/token"): token,
                ("GET", f"/commerce/notification/v1/public_key/{EBAY_KEY_ID}"): key,
                ("GET", "/commerce/notification/v1/public_key/other"): key,
            }
        )
        ebay = gateway(recorder)

        assert await ebay.notification_key(EBAY_KEY_ID) == EBAY_KEY
        await ebay.notification_key("other")

        # One application token for both keys.
        assert recorder.calls().count("POST /identity/v1/oauth2/token") == 1
        assert str(recorder.requests[1].url).startswith(API)

    async def test_an_unknown_key_is_refused(self) -> None:
        recorder = Recorder(
            {
                ("POST", "/identity/v1/oauth2/token"): httpx.Response(
                    200, json={"access_token": "app-token", "expires_in": 7200}
                ),
            }
        )

        with pytest.raises(MarketplaceRejectedError):
            await gateway(recorder).notification_key("unbekannt")

    async def test_refused_keys_of_the_app_mean_try_again_later(self) -> None:
        recorder = Recorder(
            {
                ("POST", "/identity/v1/oauth2/token"): httpx.Response(
                    401, json={"error": "invalid_client", "error_description": "disabled"}
                ),
            }
        )

        with pytest.raises(MarketplaceUnavailableError):
            await gateway(recorder).notification_key(EBAY_KEY_ID)


class TestSettings:
    def test_the_verification_token_follows_ebays_rule(self) -> None:
        with pytest.raises(ValidationError, match="32 to 80"):
            Settings(ebay_verification_token=SecretStr("zu kurz"))

    def test_production_keys_need_the_verification_token(self) -> None:
        with pytest.raises(ValidationError, match="MB_EBAY_VERIFICATION_TOKEN"):
            Settings(
                ebay_mode=MarketplaceMode.PRODUCTION,
                ebay_client_id="id",
                ebay_client_secret=SecretStr("secret"),
                ebay_ru_name="ru",
            )
