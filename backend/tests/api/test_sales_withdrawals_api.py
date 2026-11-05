"""The withdrawal function over HTTP (§ 356a BGB): anyone may declare, staff see it."""

from typing import Any, Final
from uuid import UUID

import pytest
from httpx import AsyncClient

from modellbahn.modules.catalog.application.services import CatalogService
from modellbahn.modules.media.application.services import MediaService
from modellbahn.platform.mail import InMemoryMailer
from tests.api.helpers import SHOP, assert_problem
from tests.api.test_sales_api import checkout, paid_order, put_line
from tests.conftest import SHOP_EMAIL, Deliver
from tests.media_support import InMemoryMediaStorage
from tests.sales_support import shop_product, variant_id
from tests.support import mails_to

WITHDRAWALS: Final = f"{SHOP}/withdrawals"
ADMIN_WITHDRAWALS: Final = "/api/v1/admin/withdrawals"


@pytest.fixture
async def painted(
    catalog: CatalogService,
    media: MediaService,
    media_storage: InMemoryMediaStorage,
    deliver: Deliver,
) -> UUID:
    return variant_id(await shop_product(catalog, media, media_storage, deliver), "H0", "painted")


def declaration(**changes: str) -> dict[str, str]:
    return {
        "name": "Gerda Gast",
        "order_number": "MB-2026-00042",
        "email": "gast@example.de",
        **changes,
    }


class TestWithdrawalFunction:
    async def test_a_guest_withdraws_and_gets_the_receipt(
        self,
        client: AsyncClient,
        staff_client: AsyncClient,
        deliver: Deliver,
        mailer: InMemoryMailer,
        painted: UUID,
    ) -> None:
        await put_line(client, painted, 1)
        order: dict[str, Any] = (await checkout(client)).json()

        response = await client.post(
            WITHDRAWALS,
            json=declaration(order_number=order["number"], scope="nur den Lokschuppen"),
        )
        assert response.status_code == 201, response.text
        assert response.headers["cache-control"] == "no-store"
        body = response.json()
        assert {key: body[key] for key in ("name", "order_number", "email", "scope")} == {
            "name": "Gerda Gast",
            "order_number": order["number"],
            "email": "gast@example.de",
            "scope": "nur den Lokschuppen",
        }
        assert body["received_at"]

        await deliver()
        receipt = mails_to(mailer, "gast@example.de")[-1]
        assert receipt.subject.startswith("Eingangsbestätigung: dein Widerruf")
        assert "Widerrufen: nur den Lokschuppen" in receipt.text
        assert mails_to(mailer, SHOP_EMAIL)

        listed = (await staff_client.get(ADMIN_WITHDRAWALS)).json()["items"]
        assert [(item["order_number"], item["order_id"] is not None) for item in listed] == [
            (order["number"], True)
        ]
        own = await staff_client.get(ADMIN_WITHDRAWALS, params={"order_id": listed[0]["order_id"]})
        assert len(own.json()["items"]) == 1

    async def test_an_unknown_number_gets_the_same_answer(self, client: AsyncClient) -> None:
        response = await client.post(WITHDRAWALS, json=declaration(order_number="MB-1999-00001"))
        assert response.status_code == 201
        assert set(response.json()) == {"received_at", "name", "order_number", "email", "scope"}

    @pytest.mark.parametrize(
        ("changes", "field"),
        [
            ({"name": ""}, "name"),
            ({"email": "keine-adresse"}, "email"),
            ({"order_number": ""}, "order_number"),
        ],
    )
    async def test_what_cannot_be_confirmed_is_refused(
        self, client: AsyncClient, changes: dict[str, str], field: str
    ) -> None:
        body = assert_problem(
            await client.post(WITHDRAWALS, json=declaration(**changes)), 422, "validation_failed"
        )
        assert [error["field"] for error in body["errors"]] == [field]

    async def test_only_staff_see_the_declarations(self, client: AsyncClient) -> None:
        assert_problem(await client.get(ADMIN_WITHDRAWALS), 401, "not_authenticated")


class TestRefundButton:
    async def test_staff_refund_part_and_then_the_rest(
        self,
        client: AsyncClient,
        staff_client: AsyncClient,
        deliver: Deliver,
        mailer: InMemoryMailer,
        painted: UUID,
    ) -> None:
        order = await paid_order(client, painted)  # two pieces
        order_id = (
            await staff_client.get("/api/v1/admin/orders", params={"q": order["number"]})
        ).json()["items"][0]["id"]
        refunds = f"/api/v1/admin/orders/{order_id}/refunds"

        assert_problem(
            await client.post(refunds, json={"amount_cents": 100}), 401, "not_authenticated"
        )
        too_much = await staff_client.post(
            refunds, json={"amount_cents": order["totals"]["total_cents"] + 1}
        )
        assert_problem(too_much, 409, "refund_not_possible")
        part = await staff_client.post(refunds, json={"amount_cents": 4990})
        assert part.status_code == 200, part.text
        assert part.json()["payments"][0]["refunded_cents"] == 4990
        rest = order["totals"]["total_cents"] - 4990
        done = (await staff_client.post(refunds, json={"amount_cents": rest})).json()
        assert done["payments"][0]["status"] == "refunded"

        await deliver()
        subjects = [mail.subject for mail in mails_to(mailer, "gast@example.de")]
        assert subjects.count(f"Erstattung für deine Bestellung {order['number']}") == 2
