"""Payment in advance over HTTP (ADR 0022): the choice, the details, the GiroCode, booking.

The app runs with the shop's bank account configured, next to the test payment.
"""

from collections.abc import AsyncIterator
from typing import Final
from uuid import UUID

import pytest
from asgi_lifespan import LifespanManager
from fastapi import FastAPI
from httpx import AsyncClient

from modellbahn.main import create_app
from modellbahn.modules.catalog.application.services import CatalogService, ProductDetails
from modellbahn.modules.media.application.services import MediaService
from modellbahn.platform.config import Settings
from tests.api.helpers import SHOP, assert_problem
from tests.api.test_sales_api import ADMIN_ORDERS, checkout, pay, put_line
from tests.conftest import Deliver
from tests.media_support import InMemoryMediaStorage
from tests.sales_support import shop_product, variant_id

IBAN: Final = "DE02120300000000202051"


@pytest.fixture
async def app(settings: Settings, media: MediaService) -> AsyncIterator[FastAPI]:
    with_account = settings.model_copy(
        update={
            "bank_account_holder": "Modellbahn-Shop",
            "bank_iban": IBAN,
            "bank_bic": "BYLADEM1001",
            "bank_name": "Testbank",
        }
    )
    app = create_app(with_account)
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


class TestPaymentInAdvance:
    async def test_from_choosing_to_booking(
        self, client: AsyncClient, staff_client: AsyncClient, painted: UUID
    ) -> None:
        provider = (await client.get(f"{SHOP}/payment-provider")).json()
        assert provider == {"provider": "mock", "bank_transfer": True}

        await put_line(client, painted, 1)
        placed = (await checkout(client)).json()
        token = placed["public_token"]
        assert placed["bank_transfer"] is None

        response = await pay(client, token, "bank_transfer")
        assert response.status_code == 200, response.text
        order = response.json()
        assert order["status"] == "pending_payment"
        assert order["payment_url"] is None
        transfer = order["bank_transfer"]
        assert transfer == {
            "account_holder": "Modellbahn-Shop",
            "iban": "DE02 1203 0000 0000 2020 51",
            "bic": "BYLADEM1001",
            "bank_name": "Testbank",
            "amount_cents": order["totals"]["total_cents"],
            "reference": order["number"],
            "due_at": order["payment_due_at"],
        }
        assert (await client.get(f"{SHOP}/orders/{token}")).json()["bank_transfer"] == transfer

        girocode = await client.get(f"{SHOP}/orders/{token}/girocode.svg")
        assert girocode.status_code == 200
        assert girocode.headers["content-type"] == "image/svg+xml"
        assert girocode.headers["cache-control"] == "no-store"
        assert girocode.content.startswith(b"<svg")

        (listed,) = (await staff_client.get(ADMIN_ORDERS)).json()["items"]
        booking = f"{ADMIN_ORDERS}/{listed['id']}/bank-transfer"
        booked = await staff_client.post(booking)
        assert booked.status_code == 200, booked.text
        assert booked.json()["status"] == "paid"
        assert_problem(await staff_client.post(booking), 409, "invalid_order_state")

        paid = (await client.get(f"{SHOP}/orders/{token}")).json()
        assert (paid["status"], paid["bank_transfer"]) == ("paid", None)
        assert_problem(
            await client.get(f"{SHOP}/orders/{token}/girocode.svg"), 404, "order_not_found"
        )

    async def test_packers_do_not_book_money(
        self,
        client: AsyncClient,
        staff_client: AsyncClient,
        packer_client: AsyncClient,
        painted: UUID,
    ) -> None:
        await put_line(client, painted, 1)
        token = (await checkout(client)).json()["public_token"]
        await pay(client, token, "bank_transfer")
        (listed,) = (await staff_client.get(ADMIN_ORDERS)).json()["items"]
        response = await packer_client.post(f"{ADMIN_ORDERS}/{listed['id']}/bank-transfer")
        assert_problem(response, 403, "insufficient_role")
