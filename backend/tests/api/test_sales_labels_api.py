"""Shipping labels over HTTP (ADR 0023): setup, booking, the PDF, cancelling, roles.

The app runs with the test carrier, which draws its labels itself.
"""

from collections.abc import AsyncIterator
from io import BytesIO
from typing import Any
from uuid import UUID, uuid4

import pytest
from asgi_lifespan import LifespanManager
from fastapi import FastAPI
from httpx import AsyncClient
from PIL import Image

from modellbahn.main import create_app
from modellbahn.modules.catalog.application.services import CatalogService, ProductDetails
from modellbahn.modules.media.application.services import MediaService
from modellbahn.platform.config import CarrierMode, Settings
from tests.api.helpers import assert_problem
from tests.api.test_sales_api import ADMIN_ORDERS, checkout, pay, put_line
from tests.conftest import Deliver
from tests.media_support import InMemoryMediaStorage
from tests.sales_support import shop_product, variant_id

SETUP = "/api/v1/admin/shipping/setup"


@pytest.fixture
async def app(settings: Settings, media: MediaService) -> AsyncIterator[FastAPI]:
    app = create_app(
        settings.model_copy(update={"dhl_mode": CarrierMode.TEST, "dhl_default_weight_g": 1200})
    )
    app.state.media_service = media
    async with LifespanManager(app):
        yield app


@pytest.fixture
async def painted(
    catalog: CatalogService,
    media: MediaService,
    media_storage: InMemoryMediaStorage,
    deliver: Deliver,
) -> UUID:
    product: ProductDetails = await shop_product(catalog, media, media_storage, deliver)
    return variant_id(product, "H0", "painted")


async def paid_order(client: AsyncClient, staff_client: AsyncClient, painted: UUID) -> str:
    await put_line(client, painted, 1)
    token = (await checkout(client)).json()["public_token"]
    assert (await pay(client, token, "succeeds")).status_code == 200
    (listed,) = (await staff_client.get(ADMIN_ORDERS)).json()["items"]
    order_id: str = listed["id"]
    return order_id


class TestLabels:
    async def test_setup_tells_the_stellwerk_what_it_can_do(
        self, packer_client: AsyncClient, client: AsyncClient
    ) -> None:
        response = await packer_client.get(SETUP)
        assert response.status_code == 200
        assert response.json() == {"books_labels": True, "carrier": "DHL", "default_weight_g": 1200}
        assert_problem(await client.get(SETUP), 401, "not_authenticated")

    async def test_the_packer_books_prints_and_cancels(
        self,
        client: AsyncClient,
        staff_client: AsyncClient,
        packer_client: AsyncClient,
        painted: UUID,
    ) -> None:
        order_id = await paid_order(client, staff_client, painted)
        label_url = f"{ADMIN_ORDERS}/{order_id}/shipping-label"
        assert_problem(await packer_client.get(label_url), 404, "label_not_found")

        booked = await packer_client.post(label_url, json={"weight_g": 850})
        assert booked.status_code == 201, booked.text
        label: dict[str, Any] = booked.json()
        assert label["carrier"] == "DHL"
        assert label["product"] == "V01PAK"
        assert label["weight_g"] == 850
        assert len(label["shipment_number"]) == 12
        assert (await packer_client.get(label_url)).json() == label
        assert_problem(await packer_client.post(label_url, json={}), 409, "label_exists")

        pdf = await packer_client.get(f"{label_url}.pdf")
        assert pdf.status_code == 200
        assert pdf.headers["content-type"] == "application/pdf"
        assert pdf.headers["cache-control"] == "no-store"
        assert label["shipment_number"] in pdf.headers["content-disposition"]
        assert pdf.content.startswith(b"%PDF")

        picture = await packer_client.get(f"{label_url}.png")
        assert picture.status_code == 200
        assert picture.headers["content-type"] == "image/png"
        assert label["shipment_number"] in picture.headers["content-disposition"]
        # The test label is 100 x 150 mm: at 300 dpi about 1181 x 1772 dots.
        width, height = Image.open(BytesIO(picture.content)).size
        assert (abs(width - 1181), abs(height - 1772)) <= (1, 1)

        cancelled = await packer_client.delete(label_url)
        assert cancelled.status_code == 204
        assert_problem(await packer_client.get(label_url), 404, "label_not_found")
        assert_problem(await packer_client.get(f"{label_url}.pdf"), 404, "label_not_found")
        assert_problem(await packer_client.get(f"{label_url}.png"), 404, "label_not_found")
        assert_problem(await packer_client.delete(label_url), 404, "label_not_found")

        again = await packer_client.post(label_url, json={})
        assert again.json()["weight_g"] == 1200

    async def test_refuses_what_dhl_would_not_carry(
        self,
        client: AsyncClient,
        staff_client: AsyncClient,
        painted: UUID,
    ) -> None:
        order_id = await paid_order(client, staff_client, painted)
        label_url = f"{ADMIN_ORDERS}/{order_id}/shipping-label"
        assert_problem(
            await staff_client.post(label_url, json={"weight_g": 40_000}), 422, "validation_failed"
        )
        assert_problem(
            await staff_client.post(f"{ADMIN_ORDERS}/{uuid4()}/shipping-label", json={}),
            404,
            "order_not_found",
        )

    async def test_an_unpaid_order_gets_no_label(
        self, client: AsyncClient, staff_client: AsyncClient, painted: UUID
    ) -> None:
        await put_line(client, painted, 1)
        await checkout(client)
        (listed,) = (await staff_client.get(ADMIN_ORDERS)).json()["items"]
        response = await staff_client.post(f"{ADMIN_ORDERS}/{listed['id']}/shipping-label", json={})
        assert_problem(response, 409, "invalid_order_state")

    async def test_customers_see_no_labels(
        self, client: AsyncClient, staff_client: AsyncClient, painted: UUID
    ) -> None:
        order_id = await paid_order(client, staff_client, painted)
        label_url = f"{ADMIN_ORDERS}/{order_id}/shipping-label"
        assert_problem(await client.post(label_url, json={}), 401, "not_authenticated")
        assert_problem(await client.get(f"{label_url}.pdf"), 401, "not_authenticated")


class TestWithoutCarrier:
    @pytest.fixture
    async def app(self, settings: Settings, media: MediaService) -> AsyncIterator[FastAPI]:
        app = create_app(settings)
        app.state.media_service = media
        async with LifespanManager(app):
            yield app

    async def test_the_number_is_typed_by_hand(
        self,
        client: AsyncClient,
        staff_client: AsyncClient,
        painted: UUID,
    ) -> None:
        assert (await staff_client.get(SETUP)).json()["books_labels"] is False
        order_id = await paid_order(client, staff_client, painted)
        response = await staff_client.post(f"{ADMIN_ORDERS}/{order_id}/shipping-label", json={})
        assert_problem(response, 503, "carrier_unavailable")
