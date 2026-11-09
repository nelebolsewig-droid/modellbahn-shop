"""SumUp's page over HTTP (ADR 0019): the page in the order, the way back, the webhook.

The app's sales services get the SumUp stand-in instead of the test payment.
"""

from collections.abc import AsyncIterator
from typing import Any, Final
from uuid import UUID

import pytest
from asgi_lifespan import LifespanManager
from fastapi import FastAPI
from httpx import AsyncClient

from modellbahn.main import create_app
from modellbahn.modules.catalog.application.services import CatalogService
from modellbahn.modules.media.application.services import MediaService
from modellbahn.modules.sales.application.checkout import CheckoutService
from modellbahn.modules.sales.application.common import UnitOfWorkFactory
from modellbahn.modules.sales.application.orders import OrderService
from modellbahn.modules.sales.application.payments import PaymentService
from modellbahn.platform.clock import SystemClock
from modellbahn.platform.config import Settings
from tests.api.helpers import SHOP, ClientFactory, assert_problem
from tests.api.test_sales_api import checkout, pay, put_line
from tests.conftest import PUBLIC_BASE_URL, Deliver
from tests.media_support import InMemoryMediaStorage
from tests.sales_support import FakeSumUp, shop_product, variant_id

WEBHOOK: Final = "/api/v1/webhooks/sumup"


@pytest.fixture
def sumup() -> FakeSumUp:
    return FakeSumUp()


@pytest.fixture
async def painted(
    catalog: CatalogService,
    media: MediaService,
    media_storage: InMemoryMediaStorage,
    deliver: Deliver,
) -> UUID:
    return variant_id(await shop_product(catalog, media, media_storage, deliver), "H0", "painted")


@pytest.fixture
async def app(
    settings: Settings, media: MediaService, sales_uow: UnitOfWorkFactory, sumup: FakeSumUp
) -> AsyncIterator[FastAPI]:
    app = create_app(settings)
    app.state.media_service = media
    clock = SystemClock()
    app.state.checkout_service = CheckoutService(
        uow_factory=sales_uow, clock=clock, gateway=sumup, shop_url=PUBLIC_BASE_URL
    )
    app.state.order_service = OrderService(uow_factory=sales_uow, clock=clock, gateway=sumup)
    app.state.payment_service = PaymentService(uow_factory=sales_uow, clock=clock, gateway=sumup)
    async with LifespanManager(app):
        yield app


async def on_the_page(client: AsyncClient, painted: UUID) -> dict[str, Any]:
    await put_line(client, painted, 1)
    order = (await checkout(client)).json()
    response = await pay(client, order["public_token"], "sumup")
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


class TestSumUpOverHttp:
    async def test_the_shop_names_its_provider(self, client: AsyncClient) -> None:
        response = await client.get(f"{SHOP}/payment-provider")
        assert response.status_code == 200
        assert response.json() == {"provider": "sumup", "bank_transfer": False}

    async def test_pay_on_the_page_and_come_back(
        self, client: AsyncClient, sumup: FakeSumUp, painted: UUID
    ) -> None:
        order = await on_the_page(client, painted)
        token = order["public_token"]
        assert order["status"] == "pending_payment"
        assert order["payment_url"] == "https://pay.sumup.test/chk_1"
        assert order["payments"][0]["status"] == "pending"
        assert order["payments"][0]["provider"] == "sumup"
        assert sumup.requests[0].return_url == f"{PUBLIC_BASE_URL}/bestellung/{token}/bezahlen"

        status = (await client.get(f"{SHOP}/orders/{token}")).json()
        assert status["payment_url"] == "https://pay.sumup.test/chk_1"

        sumup.pay("chk_1")
        synced = await client.post(f"{SHOP}/orders/{token}/payments/sync")
        assert synced.status_code == 200
        assert synced.headers["cache-control"] == "no-store"
        body = synced.json()
        assert (body["status"], body["payment_url"]) == ("paid", None)
        assert body["payments"][0]["status"] == "captured"
        assert_problem(
            await client.post(f"{SHOP}/orders/nope/payments/sync"), 404, "order_not_found"
        )

    async def test_an_unreachable_sumup_is_a_503(
        self, client: AsyncClient, sumup: FakeSumUp, painted: UUID
    ) -> None:
        order = await on_the_page(client, painted)
        sumup.reachable = False
        response = await client.post(f"{SHOP}/orders/{order['public_token']}/payments/sync")
        assert_problem(response, 503, "payment_unavailable")

    async def test_the_webhook_only_names_what_to_ask(
        self, make_client: ClientFactory, client: AsyncClient, sumup: FakeSumUp, painted: UUID
    ) -> None:
        order = await on_the_page(client, painted)
        sumup.pay("chk_1")
        # SumUp sends no cookie and no CSRF header.
        async with make_client(csrf=False) as sumup_server:
            for body in (
                b"",
                b"kein json",
                b"[]",
                b'{"id": 42}',
                b'{"event_type": "CHECKOUT_STATUS_CHANGED", "id": "chk_unbekannt"}',
            ):
                answer = await sumup_server.post(WEBHOOK, content=body)
                assert answer.status_code == 204, body
            status = (await client.get(f"{SHOP}/orders/{order['public_token']}")).json()
            assert status["status"] == "pending_payment"

            answer = await sumup_server.post(
                WEBHOOK, json={"event_type": "CHECKOUT_STATUS_CHANGED", "id": "chk_1"}
            )
            assert answer.status_code == 204
            assert answer.content == b""
            too_big = await sumup_server.post(WEBHOOK, content=b"x" * (16 * 1024 + 1))
            assert too_big.status_code == 413
        status = (await client.get(f"{SHOP}/orders/{order['public_token']}")).json()
        assert status["status"] == "paid"


class TestRefusedRefunds:
    async def test_the_staff_read_sumups_refusal_and_cancel_after_refunding_by_hand(
        self, client: AsyncClient, staff_client: AsyncClient, sumup: FakeSumUp, painted: UUID
    ) -> None:
        order = await on_the_page(client, painted)
        sumup.pay("chk_1")
        await client.post(f"{SHOP}/orders/{order['public_token']}/payments/sync")
        sumup.refund_refusal = "409 NOT_ALLOWED: The transaction is not eligible for a refund."
        (listed,) = (await staff_client.get("/api/v1/admin/orders")).json()["items"]
        assert listed["number"] == order["number"]
        cancel = f"/api/v1/admin/orders/{listed['id']}/cancel"

        refused = assert_problem(await staff_client.post(cancel, json={}), 409, "refund_rejected")
        assert "not eligible for a refund" in refused["detail"]

        response = await staff_client.post(cancel, json={"refunded_by_hand": True})
        assert response.status_code == 200, response.text
        body = response.json()
        assert (body["status"], body["payments"][0]["status"]) == ("cancelled", "refunded")
        assert sumup.refunds == []
