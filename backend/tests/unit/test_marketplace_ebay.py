"""The eBay adapter against recorded answers of eBay's REST APIs (httpx' MockTransport)."""

import json
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from pydantic import SecretStr, ValidationError

from modellbahn.modules.marketplace.application.ports import (
    AccessTokenRejectedError,
    AuthorizationRevokedError,
    GatewayMode,
    ListingDraft,
    LocationAddress,
    MarketplaceRejectedError,
    MarketplaceUnavailableError,
    OfferDraft,
    ShipmentReport,
)
from modellbahn.modules.marketplace.infrastructure.ebay import (
    SCOPES,
    HttpEbayGateway,
    carrier_code,
    cents,
    money,
)
from modellbahn.modules.marketplace.infrastructure.tokens import FernetTokenCipher
from modellbahn.platform.config import Environment, MarketplaceMode, Settings

API = "https://api.sandbox.ebay.com"
TOKEN = "v^1.1#access"
KEY = "ZqRBv3tHXq7d1MZFtLyLPIyxnzo-iEThHRxOPHsD_QY="

type Handler = Callable[[httpx.Request], httpx.Response]


class Recorder:
    """Answers requests from a table of (method, path) and keeps what was asked."""

    def __init__(self, answers: dict[tuple[str, str], httpx.Response | Handler]) -> None:
        self.answers = answers
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        answer = self.answers.get((request.method, request.url.path))
        if answer is None:
            return httpx.Response(404, json={"errors": [{"errorId": 0, "message": "unexpected"}]})
        return answer(request) if callable(answer) else answer

    def calls(self) -> list[str]:
        return [f"{request.method} {request.url.path}" for request in self.requests]

    def body(self, method: str, path: str) -> dict[str, Any]:
        request = next(r for r in self.requests if r.method == method and r.url.path == path)
        body: dict[str, Any] = json.loads(request.content)
        return body


def gateway(recorder: Recorder) -> HttpEbayGateway:
    return HttpEbayGateway(
        mode=GatewayMode.SANDBOX,
        client_id="adp-Shop-SBX-123",
        client_secret="SBX-secret",
        ru_name="adp-Shop-adp-Sh-abcdef",
        client=httpx.AsyncClient(transport=httpx.MockTransport(recorder)),
    )


def offer(sku: str, aspects: dict[str, list[str]], quantity: int = 3) -> OfferDraft:
    return OfferDraft(
        sku=sku,
        quantity=quantity,
        price_cents=5489,
        aspects=aspects,
        image_urls=["https://shop.test/medien/a.webp"],
    )


def draft(*offers: OfferDraft, **changes: Any) -> ListingDraft:
    values: dict[str, Any] = {
        "group_key": "MB-000042-H0",
        "title": "IFA W50 Kipper H0 1:87 Fertigmodell adp-Modelle",
        "description_html": "<p>Kipper</p>",
        "category_id": "180250",
        "aspects": {"Marke": ["adp-Modelle"], "Maßstab": ["1:87"]},
        "image_urls": ["https://shop.test/medien/a.webp"],
        "offers": list(offers),
        "varies_by": ["Ausführung"] if len(offers) > 1 else [],
        "fulfillment_policy_id": "F1",
        "payment_policy_id": "P1",
        "return_policy_id": "R1",
        "location_key": "werkstatt",
    }
    values.update(changes)
    return ListingDraft(**values)


INVENTORY = "/sell/inventory/v1"


class TestOAuth:
    def test_the_consent_page_asks_for_the_shops_scopes(self) -> None:
        url = gateway(Recorder({})).authorize_url("STATE-123")
        parts = urlsplit(url)
        query = parse_qs(parts.query)
        assert parts.netloc == "auth.sandbox.ebay.com"
        assert query["redirect_uri"] == ["adp-Shop-adp-Sh-abcdef"]
        assert query["state"] == ["STATE-123"]
        assert query["scope"][0].split(" ") == list(SCOPES)

    async def test_the_code_becomes_tokens(self) -> None:
        def answer(request: httpx.Request) -> httpx.Response:
            assert request.headers["Authorization"].startswith("Basic ")
            assert parse_qs(request.content.decode())["grant_type"] == ["authorization_code"]
            return httpx.Response(
                200,
                json={
                    "access_token": TOKEN,
                    "expires_in": 7200,
                    "refresh_token": "v^1.1#refresh",
                    "refresh_token_expires_in": 47304000,
                },
            )

        recorder = Recorder({("POST", "/identity/v1/oauth2/token"): answer})
        grant = await gateway(recorder).exchange_code("code")
        assert grant.access_token == TOKEN
        assert grant.refresh_token == "v^1.1#refresh"
        assert (grant.refresh_expires_at - grant.access_expires_at).days == 547

    async def test_a_refused_refresh_token_means_consent_again(self) -> None:
        recorder = Recorder(
            {
                ("POST", "/identity/v1/oauth2/token"): httpx.Response(
                    400, json={"error": "invalid_grant", "error_description": "expired"}
                )
            }
        )
        with pytest.raises(AuthorizationRevokedError):
            await gateway(recorder).refresh("old")


class TestPublish:
    async def test_one_choice_is_one_offer(self) -> None:
        recorder = Recorder(
            {
                ("PUT", f"{INVENTORY}/inventory_item/MB-000042-H0-F"): httpx.Response(204),
                ("GET", f"{INVENTORY}/offer"): httpx.Response(404),
                ("POST", f"{INVENTORY}/offer"): httpx.Response(201, json={"offerId": "O-1"}),
                ("POST", f"{INVENTORY}/offer/O-1/publish"): httpx.Response(
                    200, json={"listingId": "110012345678"}
                ),
            }
        )
        published = await gateway(recorder).publish(
            TOKEN, draft(offer("MB-000042-H0-F", {"Ausführung": ["Fertigmodell"]}))
        )
        assert published.external_id == "110012345678"
        assert published.offer_ids == {"MB-000042-H0-F": "O-1"}
        item = recorder.body("PUT", f"{INVENTORY}/inventory_item/MB-000042-H0-F")
        assert item["availability"]["shipToLocationAvailability"]["quantity"] == 3
        assert item["product"]["aspects"]["Ausführung"] == ["Fertigmodell"]
        assert item["product"]["ean"] == ["Nicht zutreffend"]
        created = recorder.body("POST", f"{INVENTORY}/offer")
        assert created["pricingSummary"]["price"] == {"value": "54.89", "currency": "EUR"}
        assert created["listingDescription"] == "<p>Kipper</p>"
        assert recorder.requests[0].headers["Content-Language"] == "de-DE"
        assert recorder.requests[0].headers["Authorization"] == f"Bearer {TOKEN}"

    async def test_several_choices_are_an_item_group(self) -> None:
        recorder = Recorder(
            {
                ("PUT", f"{INVENTORY}/inventory_item/MB-000042-H0-B"): httpx.Response(204),
                ("PUT", f"{INVENTORY}/inventory_item/MB-000042-H0-F"): httpx.Response(204),
                ("PUT", f"{INVENTORY}/offer/O-B"): httpx.Response(204),
                ("PUT", f"{INVENTORY}/offer/O-F"): httpx.Response(204),
                ("PUT", f"{INVENTORY}/inventory_item_group/MB-000042-H0"): httpx.Response(204),
                ("POST", f"{INVENTORY}/offer/publish_by_inventory_item_group"): httpx.Response(
                    200, json={"listingId": "110099999999"}
                ),
            }
        )
        published = await gateway(recorder).publish(
            TOKEN,
            draft(
                offer("MB-000042-H0-B", {"Ausführung": ["Bausatz"]}),
                offer("MB-000042-H0-F", {"Ausführung": ["Fertigmodell"]}),
                known_offer_ids={"MB-000042-H0-B": "O-B", "MB-000042-H0-F": "O-F"},
                previous_external_id="110099999999",
                previous_skus=["MB-000042-H0-B", "MB-000042-H0-F"],
            ),
        )
        assert published.external_id == "110099999999"
        group = recorder.body("PUT", f"{INVENTORY}/inventory_item_group/MB-000042-H0")
        assert group["variantSKUs"] == ["MB-000042-H0-B", "MB-000042-H0-F"]
        assert group["variesBy"]["specifications"] == [
            {"name": "Ausführung", "values": ["Bausatz", "Fertigmodell"]}
        ]
        # Known offers are rewritten, not created again.
        assert f"POST {INVENTORY}/offer" not in recorder.calls()

    async def test_from_one_to_several_choices_ends_the_old_listing(self) -> None:
        recorder = Recorder(
            {
                ("POST", f"{INVENTORY}/offer/O-F/withdraw"): httpx.Response(200, json={}),
                ("PUT", f"{INVENTORY}/inventory_item/MB-000042-H0-B"): httpx.Response(204),
                ("PUT", f"{INVENTORY}/inventory_item/MB-000042-H0-F"): httpx.Response(204),
                ("GET", f"{INVENTORY}/offer"): httpx.Response(404),
                ("POST", f"{INVENTORY}/offer"): httpx.Response(201, json={"offerId": "O-B"}),
                ("PUT", f"{INVENTORY}/offer/O-F"): httpx.Response(204),
                ("PUT", f"{INVENTORY}/inventory_item_group/MB-000042-H0"): httpx.Response(204),
                ("POST", f"{INVENTORY}/offer/publish_by_inventory_item_group"): httpx.Response(
                    200, json={"listingId": "110077777777"}
                ),
            }
        )
        await gateway(recorder).publish(
            TOKEN,
            draft(
                offer("MB-000042-H0-B", {"Ausführung": ["Bausatz"]}),
                offer("MB-000042-H0-F", {"Ausführung": ["Fertigmodell"]}),
                known_offer_ids={"MB-000042-H0-F": "O-F"},
                previous_external_id="110012345678",
                previous_skus=["MB-000042-H0-F"],
            ),
        )
        assert recorder.calls()[0] == f"POST {INVENTORY}/offer/O-F/withdraw"

    async def test_ebays_refusal_carries_its_error(self) -> None:
        recorder = Recorder(
            {
                ("PUT", f"{INVENTORY}/inventory_item/X"): httpx.Response(
                    400,
                    json={
                        "errors": [
                            {
                                "errorId": 25709,
                                "message": "Invalid value",
                                "longMessage": "Invalid value for imageUrls.",
                            }
                        ]
                    },
                )
            }
        )
        with pytest.raises(MarketplaceRejectedError) as caught:
            await gateway(recorder).publish(TOKEN, draft(offer("X", {})))
        assert caught.value.code == "25709"
        assert caught.value.message == "Invalid value for imageUrls."

    @pytest.mark.parametrize(
        ("status", "error"),
        [
            (401, AccessTokenRejectedError),
            (429, MarketplaceUnavailableError),
            (503, MarketplaceUnavailableError),
        ],
    )
    async def test_waiting_is_not_refusing(self, status: int, error: type[Exception]) -> None:
        recorder = Recorder(
            {("PUT", f"{INVENTORY}/inventory_item/X"): httpx.Response(status, json={})}
        )
        with pytest.raises(error):
            await gateway(recorder).publish(TOKEN, draft(offer("X", {})))

    async def test_no_network_is_unavailable(self) -> None:
        def broken(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("no route", request=request)

        with pytest.raises(MarketplaceUnavailableError):
            await gateway(Recorder({("GET", "/commerce/identity/v1/user/"): broken})).seller_name(
                TOKEN
            )


class TestAccount:
    async def test_policies_of_each_kind(self) -> None:
        recorder = Recorder(
            {
                ("GET", "/sell/account/v1/fulfillment_policy"): httpx.Response(
                    200,
                    json={"fulfillmentPolicies": [{"fulfillmentPolicyId": "F1", "name": "DHL"}]},
                ),
                ("GET", "/sell/account/v1/payment_policy"): httpx.Response(
                    200, json={"paymentPolicies": [{"paymentPolicyId": "P1", "name": "eBay"}]}
                ),
                ("GET", "/sell/account/v1/return_policy"): httpx.Response(
                    200, json={"returnPolicies": []}
                ),
            }
        )
        policies = await gateway(recorder).policies(TOKEN)
        assert [p.id for p in policies.fulfillment] == ["F1"]
        assert [p.name for p in policies.payment] == ["eBay"]
        assert list(policies.returns) == []
        assert recorder.requests[0].url.params["marketplace_id"] == "EBAY_DE"

    async def test_the_location_is_created_once(self) -> None:
        recorder = Recorder(
            {
                ("GET", f"{INVENTORY}/location/werkstatt"): httpx.Response(404),
                ("POST", f"{INVENTORY}/location/werkstatt"): httpx.Response(204),
            }
        )
        address = LocationAddress("adp-Modelle", "Musterstraße 1", "12345", "Musterstadt", "DE")
        await gateway(recorder).ensure_location(TOKEN, "werkstatt", address)
        created = recorder.body("POST", f"{INVENTORY}/location/werkstatt")
        assert created["location"]["address"]["postalCode"] == "12345"

        known = Recorder(
            {
                ("GET", f"{INVENTORY}/location/werkstatt"): httpx.Response(
                    200, json={"merchantLocationKey": "werkstatt"}
                )
            }
        )
        await gateway(known).ensure_location(TOKEN, "werkstatt", address)
        assert known.calls() == [f"GET {INVENTORY}/location/werkstatt"]


ORDER = {
    "orderId": "12-34567-89012",
    "creationDate": "2026-10-22T08:00:00.000Z",
    "orderPaymentStatus": "PAID",
    "cancelStatus": {"cancelState": "NONE_REQUESTED"},
    "buyer": {"username": "erika_kauft", "buyerRegistrationAddress": {"email": "r@example.de"}},
    "pricingSummary": {"deliveryCost": {"value": "5.90", "currency": "EUR"}},
    "paymentSummary": {"payments": [{"paymentDate": "2026-10-22T08:05:00.000Z"}]},
    "fulfillmentStartInstructions": [
        {
            "shippingStep": {
                "shipTo": {
                    "fullName": "Erika Mustermann",
                    "email": "erika@members.ebay.de",
                    "contactAddress": {
                        "addressLine1": "Bahnhofstraße 12",
                        "addressLine2": "Hinterhaus",
                        "city": "Altenau",
                        "postalCode": "38707",
                        "countryCode": "DE",
                    },
                }
            }
        }
    ],
    "lineItems": [
        {
            "lineItemId": "10001",
            "sku": "MB-000042-H0-F",
            "title": "IFA W50 Kipper",
            "quantity": 2,
            "lineItemCost": {"value": "109.78", "currency": "EUR"},
        }
    ],
}


class TestOrders:
    async def test_orders_in_the_shops_terms(self) -> None:
        recorder = Recorder(
            {
                ("GET", "/sell/fulfillment/v1/order"): httpx.Response(
                    200, json={"orders": [ORDER], "total": 1}
                )
            }
        )
        (order,) = await gateway(recorder).orders(
            TOKEN,
            modified_since=datetime(2026, 10, 22, 7, 50, tzinfo=UTC),
            until=datetime(2026, 10, 22, 10, 0, 0, 123000, tzinfo=UTC),
        )
        window = recorder.requests[0].url.params["filter"]
        assert window == "lastmodifieddate:[2026-10-22T07:50:00.000Z..2026-10-22T10:00:00.123Z]"
        assert order.external_id == "12-34567-89012"
        assert order.street == "Bahnhofstraße 12, Hinterhaus"
        assert order.email == "erika@members.ebay.de"
        assert order.shipping_cents == 590
        assert order.paid
        assert not order.cancelled
        assert order.paid_at == datetime(2026, 10, 22, 8, 5, tzinfo=UTC)
        (line,) = order.lines
        assert (line.quantity, line.unit_price_cents) == (2, 5489)

    async def test_pages_are_followed(self) -> None:
        def page(request: httpx.Request) -> httpx.Response:
            offset = int(request.url.params["offset"])
            orders = [
                {**ORDER, "orderId": f"12-{offset + i}"} for i in range(50 if not offset else 3)
            ]
            return httpx.Response(200, json={"orders": orders, "total": 53})

        recorder = Recorder({("GET", "/sell/fulfillment/v1/order"): page})
        found = await gateway(recorder).orders(
            TOKEN, modified_since=datetime(2026, 10, 1, tzinfo=UTC), until=datetime.now(UTC)
        )
        assert len(found) == 53
        assert len(recorder.requests) == 2

    async def test_the_shipment_goes_back_with_ebays_carrier_code(self) -> None:
        path = "/sell/fulfillment/v1/order/12-34567-89012/shipping_fulfillment"
        recorder = Recorder({("POST", path): httpx.Response(201)})
        await gateway(recorder).report_shipment(
            TOKEN,
            ShipmentReport(
                external_id="12-34567-89012",
                lines=[("10001", 2)],
                carrier="Deutsche Post",
                tracking_number="00340434161234567890",
                shipped_at=datetime(2026, 10, 23, 9, 30, tzinfo=UTC),
            ),
        )
        body = recorder.body("POST", path)
        assert body == {
            "lineItems": [{"lineItemId": "10001", "quantity": 2}],
            "shippedDate": "2026-10-23T09:30:00.000Z",
            "shippingCarrierCode": "DEUTSCHE_POST",
            "trackingNumber": "00340434161234567890",
        }


def test_money_both_ways() -> None:
    assert money(5489) == {"value": "54.89", "currency": "EUR"}
    assert money(5) == {"value": "0.05", "currency": "EUR"}
    assert cents({"value": "54.89"}) == 5489
    assert cents(None) == 0


def test_carrier_codes() -> None:
    assert carrier_code("dhl") == "DHL"
    assert carrier_code(" Deutsche  Post ") == "DEUTSCHE_POST"
    assert carrier_code("Royal Mail") == "ROYAL_MAIL"


class TestTokenCipher:
    def test_tokens_are_sealed_and_opened(self) -> None:
        cipher = FernetTokenCipher(KEY)
        sealed = cipher.encrypt(TOKEN)
        assert TOKEN not in sealed
        assert cipher.decrypt(sealed) == TOKEN
        assert cipher.encrypt("") == ""

    def test_another_key_opens_nothing(self) -> None:
        sealed = FernetTokenCipher(KEY).encrypt(TOKEN)
        other = FernetTokenCipher("q6hYGcJ8cS4bJ3Hh1k8x9vI3l6m9yKk1pJ0yZp2bQhU=")
        assert other.decrypt(sealed) == ""


class TestSettings:
    def test_sandbox_needs_the_keys_of_the_developer_account(self) -> None:
        with pytest.raises(ValidationError, match="MB_EBAY_CLIENT_ID"):
            Settings(ebay_mode=MarketplaceMode.SANDBOX)

    def test_the_token_key_must_be_a_fernet_key(self) -> None:
        with pytest.raises(ValidationError, match="Fernet"):
            Settings(ebay_token_key=SecretStr("zu-kurz"))

    @pytest.mark.parametrize("mode", [MarketplaceMode.TEST, MarketplaceMode.SANDBOX])
    def test_production_sells_on_the_real_ebay_only(self, mode: MarketplaceMode) -> None:
        with pytest.raises(ValidationError, match="not allowed in production"):
            Settings(
                environment=Environment.PRODUCTION,
                s3_access_key_id="GK0123456789abcdef01234567",
                imprint_company="Muster",
                imprint_owner="Max Muster",
                imprint_street="Musterstraße 1",
                imprint_postal_code="12345",
                imprint_city="Musterstadt",
                imprint_email="info@example.com",
                ebay_mode=mode,
                ebay_client_id="id",
                ebay_client_secret=SecretStr("secret"),
                ebay_ru_name="ru",
            )
