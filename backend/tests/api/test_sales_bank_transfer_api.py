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


REPAYMENTS: Final = "/api/v1/admin/repayments"
CUSTOMER_IBAN: Final = "DE89370400440532013000"


class TestRepayment:
    """Money paid by transfer goes back by hand, with a GiroCode for the staff (ADR 0040)."""

    async def cancelled_after_transfer(
        self, client: AsyncClient, staff_client: AsyncClient, painted: UUID
    ) -> str:
        await put_line(client, painted, 1)
        token = (await checkout(client)).json()["public_token"]
        await pay(client, token, "bank_transfer")
        (listed,) = (await staff_client.get(ADMIN_ORDERS)).json()["items"]
        await staff_client.post(f"{ADMIN_ORDERS}/{listed['id']}/bank-transfer")
        cancelled = await staff_client.post(f"{ADMIN_ORDERS}/{listed['id']}/cancel", json={})
        assert cancelled.status_code == 200, cancelled.text
        return str(listed["id"])

    async def test_from_the_refund_to_the_transfer_back(
        self, client: AsyncClient, staff_client: AsyncClient, painted: UUID
    ) -> None:
        order_id = await self.cancelled_after_transfer(client, staff_client, painted)
        order = (await staff_client.get(f"{ADMIN_ORDERS}/{order_id}")).json()
        total = order["totals"]["total_cents"]
        assert order["repayment"] == {
            "amount_cents": total,
            "holder": None,
            "iban": None,
            "reference": f"Erstattung {order['number']}",
        }
        (listed,) = (await staff_client.get(REPAYMENTS)).json()["items"]
        assert listed == {
            "order_id": order_id,
            "number": order["number"],
            "recipient": "Erika Mustermann",
            "amount_cents": total,
            "has_account": False,
        }
        girocode = f"{ADMIN_ORDERS}/{order_id}/repayment/girocode.svg"
        assert_problem(await staff_client.get(girocode), 404, "order_not_found")

        account = f"{ADMIN_ORDERS}/{order_id}/repayment"
        assert_problem(
            await staff_client.put(
                account, json={"holder": "Erika", "iban": "DE00 1234 5678 9012"}
            ),
            422,
            "validation_failed",
        )
        saved = await staff_client.put(
            account, json={"holder": " Erika  Mustermann ", "iban": "de89 3704 0044 0532 0130 00"}
        )
        assert saved.status_code == 200, saved.text
        assert saved.json()["repayment"]["holder"] == "Erika Mustermann"
        assert saved.json()["repayment"]["iban"] == "DE89 3704 0044 0532 0130 00"
        assert (await staff_client.get(REPAYMENTS)).json()["items"][0]["has_account"] is True

        code = await staff_client.get(girocode)
        assert code.status_code == 200
        assert code.headers["content-type"] == "image/svg+xml"
        assert code.headers["cache-control"] == "no-store"
        assert code.content.startswith(b"<svg")

        done = await staff_client.post(f"{account}/done")
        assert done.status_code == 200, done.text
        assert done.json()["repayment"] is None
        assert (await staff_client.get(REPAYMENTS)).json()["items"] == []
        assert_problem(await staff_client.get(girocode), 404, "order_not_found")
        assert_problem(await staff_client.post(f"{account}/done"), 409, "invalid_order_state")
        assert_problem(
            await staff_client.put(account, json={"holder": "Erika", "iban": CUSTOMER_IBAN}),
            409,
            "invalid_order_state",
        )

    async def test_the_customer_never_sees_the_account(
        self, client: AsyncClient, staff_client: AsyncClient, painted: UUID
    ) -> None:
        order_id = await self.cancelled_after_transfer(client, staff_client, painted)
        await staff_client.put(
            f"{ADMIN_ORDERS}/{order_id}/repayment",
            json={"holder": "Erika Mustermann", "iban": CUSTOMER_IBAN},
        )
        token = (await staff_client.get(f"{ADMIN_ORDERS}/{order_id}")).json()["public_token"]
        status = (await client.get(f"{SHOP}/orders/{token}")).json()
        assert "repayment" not in status
        assert CUSTOMER_IBAN not in str(status)

    async def test_packers_do_not_handle_money(
        self,
        client: AsyncClient,
        staff_client: AsyncClient,
        packer_client: AsyncClient,
        painted: UUID,
    ) -> None:
        order_id = await self.cancelled_after_transfer(client, staff_client, painted)
        assert_problem(await packer_client.get(REPAYMENTS), 403, "insufficient_role")
        assert_problem(
            await packer_client.post(f"{ADMIN_ORDERS}/{order_id}/repayment/done"),
            403,
            "insufficient_role",
        )
