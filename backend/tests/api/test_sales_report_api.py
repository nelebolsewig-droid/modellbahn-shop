"""The sales report over HTTP (ADR 0039): paid orders and pieces sold at a fair in one list,
the channel and price of a piece booked out, entered then or afterwards."""

from datetime import datetime, timedelta
from typing import Any
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import pytest
from httpx import AsyncClient

from modellbahn.modules.catalog.application.services import CatalogService, ProductDetails
from modellbahn.modules.media.application.services import MediaService
from tests.api.helpers import assert_problem
from tests.api.test_sales_api import paid_order
from tests.conftest import Deliver
from tests.media_support import InMemoryMediaStorage
from tests.sales_support import shop_product, variant_id

INVENTORY = "/api/v1/admin/inventory"
REPORT = "/api/v1/admin/sales/report"


@pytest.fixture
async def product(
    catalog: CatalogService,
    media: MediaService,
    media_storage: InMemoryMediaStorage,
    deliver: Deliver,
) -> ProductDetails:
    return await shop_product(catalog, media, media_storage, deliver)


@pytest.fixture
def painted(product: ProductDetails) -> UUID:
    return variant_id(product, "H0", "painted")


def today() -> str:
    return datetime.now(ZoneInfo("Europe/Berlin")).date().isoformat()


async def report(client: AsyncClient, start: str, end: str) -> dict[str, Any]:
    response = await client.get(REPORT, params={"start": start, "end": end})
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


async def stock_up(staff: AsyncClient, variant: UUID, quantity: int) -> list[str]:
    await staff.post(f"{INVENTORY}/locations/shelves", json={"levels": 1})
    response = await staff.post(
        f"{INVENTORY}/units",
        json={"variant_id": str(variant), "quantity": quantity, "location_code": "R01-B01"},
    )
    assert response.status_code == 201, response.text
    listed = await staff.get(f"{INVENTORY}/units", params={"variant_id": str(variant)})
    return [unit["code"] for unit in listed.json()["items"]]


class TestSalesReport:
    async def test_orders_and_pieces_sold_at_a_fair(
        self,
        client: AsyncClient,
        staff_client: AsyncClient,
        painted: UUID,
        product: ProductDetails,
    ) -> None:
        shop_price = next(
            v.price_cents for s in product.product.scales for v in s.variants if v.id == painted
        )
        first, second, third, *_ = await stock_up(staff_client, painted, 5)
        # At the fair with a price, by scan without one, and one broken (no sale).
        at_fair = await staff_client.post(
            f"{INVENTORY}/units/{first}/scrap",
            json={"reason": "sold", "channel": "fair", "price_cents": 3500, "note": "Leipzig"},
        )
        assert (at_fair.json()["sale_channel"], at_fair.json()["sale_price_cents"]) == (
            "fair",
            3500,
        ), at_fair.text
        await staff_client.post(f"{INVENTORY}/units/{second}/scrap", json={"reason": "sold"})
        broken = await staff_client.post(
            f"{INVENTORY}/units/{third}/scrap",
            json={"reason": "damaged", "channel": "fair", "price_cents": 100},
        )
        assert (broken.json()["sale_channel"], broken.json()["sale_price_cents"]) == (None, None)
        order = await paid_order(client, painted)

        body = await report(staff_client, today(), today())
        lines = {line["key"]: line for line in body["lines"]}
        assert {first, second} < set(lines)
        assert len(lines) == 3
        assert (lines[first]["channel"], lines[first]["total_cents"]) == ("fair", 3500)
        assert (lines[first]["price_from_shop"], lines[first]["note"]) == (False, "Leipzig")
        assert lines[first]["staff_name"] == "Chefin"
        # Model and scale, for the evaluation: the same for a piece and an order line.
        (online_line,) = [line for line in body["lines"] if line["kind"] == "order_line"]
        for line in (lines[first], online_line):
            assert (line["scale_code"], line["variant_id"]) == ("H0", str(painted))
            assert line["product_name"]
            assert line["product_name"] in line["title"]
            assert line["variant_name"].startswith("H0")
        assert (lines[second]["channel"], lines[second]["unit_price_cents"]) == (
            "unknown",
            shop_price,
        )
        assert lines[second]["price_from_shop"] is True
        (online,) = [line for line in body["lines"] if line["kind"] == "order_line"]
        assert (online["channel"], online["quantity"], online["order_number"]) == (
            "shop",
            2,
            order["number"],
        )

        # Entered afterwards: Johann sold it for less at the fair.
        corrected = await staff_client.put(
            f"{INVENTORY}/units/{second}/sale", json={"channel": "fair", "price_cents": 2900}
        )
        assert corrected.status_code == 200, corrected.text
        again = {
            line["key"]: line for line in (await report(staff_client, today(), today()))["lines"]
        }
        assert (again[second]["channel"], again[second]["total_cents"]) == ("fair", 2900)
        assert again[second]["price_from_shop"] is False

        # Only a piece sold has a sale; a piece booked in again leaves the report.
        assert_problem(
            await staff_client.put(f"{INVENTORY}/units/{third}/sale", json={"channel": "fair"}),
            409,
            "invalid_unit_state",
        )
        restored = await staff_client.post(
            f"{INVENTORY}/units/restores",
            json={"unit_ids": [at_fair.json()["id"]], "location_code": "R01-B01"},
        )
        assert restored.status_code == 200, restored.text
        keys = {line["key"] for line in (await report(staff_client, today(), today()))["lines"]}
        assert first not in keys

    async def test_other_days_are_empty_and_spans_are_checked(
        self, staff_client: AsyncClient, packer_client: AsyncClient, painted: UUID
    ) -> None:
        (code, *_) = await stock_up(staff_client, painted, 1)
        await staff_client.post(f"{INVENTORY}/units/{code}/scrap", json={"reason": "sold"})
        yesterday = (datetime.now(ZoneInfo("Europe/Berlin")).date() - timedelta(days=1)).isoformat()
        assert (await report(staff_client, yesterday, yesterday))["lines"] == []
        assert_problem(
            await staff_client.get(REPORT, params={"start": today(), "end": yesterday}),
            422,
            "validation_failed",
        )
        assert_problem(
            await staff_client.get(REPORT, params={"start": "2024-01-01", "end": "2025-12-31"}),
            422,
            "validation_failed",
        )
        assert_problem(
            await packer_client.get(REPORT, params={"start": today(), "end": today()}),
            403,
            "insufficient_role",
        )

    async def test_the_scanner_books_out_to_the_channel_chosen(
        self, staff_client: AsyncClient, painted: UUID, product: ProductDetails
    ) -> None:
        await stock_up(staff_client, painted, 3)
        gtin = next(v.gtin for s in product.product.scales for v in s.variants if v.id == painted)
        body = {
            "scan_id": str(uuid4()),
            "raw": gtin,
            "mode": "scrap",
            "source": "camera",
            "quantity": 2,
            "context": {"reason": "sold", "channel": "store"},
        }
        scanned = await staff_client.post(f"{INVENTORY}/scans", json=body)
        assert scanned.json()["outcome"] == "applied", scanned.text
        lines = (await report(staff_client, today(), today()))["lines"]
        assert [(line["channel"], line["price_from_shop"]) for line in lines] == [
            ("store", True),
            ("store", True),
        ]
        wrong = {**body, "scan_id": str(uuid4()), "context": {"channel": "flohmarkt"}}
        assert_problem(
            await staff_client.post(f"{INVENTORY}/scans", json=wrong), 422, "validation_failed"
        )
