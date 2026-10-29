"""The inventory API: locations, units, scans, pick lists, labels, availability, articles."""

import csv
import io
from typing import Any
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient

from modellbahn.modules.catalog.application.services import CatalogService, ProductDetails
from modellbahn.modules.media.application.services import MediaService
from tests.api.helpers import SHOP, assert_problem
from tests.conftest import Deliver
from tests.media_support import InMemoryMediaStorage
from tests.sales_support import shop_product, variant_id

INVENTORY = "/api/v1/admin/inventory"


@pytest.fixture
async def product(
    catalog: CatalogService,
    media: MediaService,
    media_storage: InMemoryMediaStorage,
    deliver: Deliver,
) -> ProductDetails:
    return await shop_product(catalog, media, media_storage, deliver, made_to_order=False)


@pytest.fixture
def painted(product: ProductDetails) -> UUID:
    return variant_id(product, "H0", "painted")


async def build_store(staff: AsyncClient) -> None:
    for body in (
        {"segment": "LAGER", "kind": "site", "name": "Werkstatt"},
        {"parent_code": "LAGER", "segment": "R01", "kind": "shelf", "name": "Regal 1"},
        {"parent_code": "R01", "segment": "F01", "kind": "compartment"},
    ):
        response = await staff.post(f"{INVENTORY}/locations", json=body)
        assert response.status_code == 201, response.text


async def scan(staff: AsyncClient, raw: str, mode: str, **context: str) -> dict[str, Any]:
    response = await staff.post(
        f"{INVENTORY}/scans",
        json={
            "scan_id": str(uuid4()),
            "raw": raw,
            "mode": mode,
            "source": "camera",
            "context": context,
        },
    )
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


class TestLocations:
    async def test_build_rename_look_inside_and_remove(self, staff_client: AsyncClient) -> None:
        await build_store(staff_client)
        tree = (await staff_client.get(f"{INVENTORY}/locations")).json()["items"]
        assert [(n["code"], n["path"], n["holds_goods"]) for n in tree] == [
            ("LAGER", "LAGER", False),
            ("R01", "LAGER.R01", False),
            ("R01-F01", "LAGER.R01.F01", True),
        ]
        renamed = await staff_client.patch(f"{INVENTORY}/locations/r01", json={"name": "Fenster"})
        assert renamed.json()["name"] == "Fenster"
        inside = (await staff_client.get(f"{INVENTORY}/locations/R01")).json()
        assert [c["code"] for c in inside["children"]] == ["R01-F01"]
        assert [a["code"] for a in inside["ancestors"]] == ["LAGER"]
        assert (await staff_client.delete(f"{INVENTORY}/locations/R01-F01")).status_code == 204
        assert_problem(
            await staff_client.delete(f"{INVENTORY}/locations/LAGER"), 409, "location_not_empty"
        )

    async def test_refusals(self, staff_client: AsyncClient) -> None:
        await build_store(staff_client)
        assert_problem(
            await staff_client.post(
                f"{INVENTORY}/locations",
                json={"parent_code": "LAGER", "segment": "R01", "kind": "shelf"},
            ),
            409,
            "location_code_taken",
        )
        body = assert_problem(
            await staff_client.post(
                f"{INVENTORY}/locations",
                json={"parent_code": "LAGER", "segment": "X1", "kind": "box"},
            ),
            422,
            "validation_failed",
        )
        assert body["errors"][0]["code"] == "invalid_parent"
        assert_problem(
            await staff_client.get(f"{INVENTORY}/locations/NIRGENDS"), 404, "location_not_found"
        )

    async def test_packers_scan_but_do_not_build(
        self, packer_client: AsyncClient, client: AsyncClient
    ) -> None:
        assert (await packer_client.get(f"{INVENTORY}/locations")).status_code == 200
        assert_problem(
            await packer_client.post(
                f"{INVENTORY}/locations", json={"segment": "X", "kind": "site"}
            ),
            403,
            "insufficient_role",
        )
        assert_problem(await client.get(f"{INVENTORY}/stock"), 401, "not_authenticated")


class TestUnitsAndScans:
    async def test_label_store_look_up_scrap(
        self, staff_client: AsyncClient, painted: UUID
    ) -> None:
        await build_store(staff_client)
        created = await staff_client.post(
            f"{INVENTORY}/units", json={"variant_id": str(painted), "quantity": 2}
        )
        assert created.status_code == 201, created.text
        first, second = created.json()["items"]
        assert (first["status"], first["variant"]["variant_id"]) == ("labeled", str(painted))
        assert first["display_code"].replace(" ", "") == first["code"]

        selected = await scan(staff_client, "R01-F01", "put_away")
        assert selected["outcome"] == "selected"
        stored = await scan(staff_client, first["code"], "put_away", location_code="R01-F01")
        assert (stored["outcome"], stored["effect"]["to_location"]) == ("applied", "R01-F01")
        undone = await staff_client.post(f"{INVENTORY}/scans/{stored['scan_id']}/undo")
        assert undone.json()["undone"] is True
        assert_problem(
            await staff_client.post(f"{INVENTORY}/scans/{stored['scan_id']}/undo"),
            409,
            "scan_already_undone",
        )
        await scan(staff_client, second["code"], "put_away", location_code="R01-F01")

        details = (await staff_client.get(f"{INVENTORY}/units/{second['code']}")).json()
        assert [h["reason"] for h in details["history"]] == ["label", "put_away"]
        assert details["location"]["code"] == "R01-F01"
        stock = (await staff_client.get(f"{INVENTORY}/stock")).json()["items"]
        assert [(s["labeled"], s["in_stock"]) for s in stock] == [(1, 1)]

        scrapped = await staff_client.post(
            f"{INVENTORY}/units/{second['code']}/scrap", json={"note": "Dach gebrochen"}
        )
        assert (scrapped.json()["status"], scrapped.json()["scrap_note"]) == (
            "scrapped",
            "Dach gebrochen",
        )
        assert_problem(
            await staff_client.post(f"{INVENTORY}/units/{second['code']}/scrap", json={}),
            409,
            "invalid_unit_state",
        )
        assert_problem(
            await staff_client.get(f"{INVENTORY}/units/0000000000"), 404, "unit_not_found"
        )

    async def test_a_reused_scan_id_is_refused(
        self, staff_client: AsyncClient, painted: UUID
    ) -> None:
        await build_store(staff_client)
        body = {"scan_id": str(uuid4()), "raw": "R01-F01", "mode": "lookup", "source": "camera"}
        first = await staff_client.post(f"{INVENTORY}/scans", json=body)
        again = await staff_client.post(f"{INVENTORY}/scans", json=body)
        assert first.json() == again.json()
        assert_problem(
            await staff_client.post(f"{INVENTORY}/scans", json={**body, "raw": "R01"}),
            409,
            "scan_id_reused",
        )
        assert_problem(
            await staff_client.post(f"{INVENTORY}/scans/{uuid4()}/undo"), 404, "scan_not_found"
        )


class TestPicking:
    async def test_pay_allocate_pick_list(
        self,
        client: AsyncClient,
        staff_client: AsyncClient,
        deliver: Deliver,
        painted: UUID,
    ) -> None:
        await build_store(staff_client)
        await staff_client.post(
            f"{INVENTORY}/units",
            json={"variant_id": str(painted), "quantity": 1, "location_code": "R01-F01"},
        )
        assert (await client.put(f"{SHOP}/cart/lines/{painted}", json={"quantity": 1})).is_success
        cart = (await client.get(f"{SHOP}/cart")).json()
        assert cart["lines"][0]["availability"] == "in_stock"
        order = await client.post(
            f"{SHOP}/checkouts",
            headers={"Idempotency-Key": str(uuid4())},
            json={
                "expected_total_cents": cart["totals"]["total_cents"],
                "email": "erika@example.de",
                "address": {
                    "recipient": "Erika Mustermann",
                    "street": "Bahnhofstraße 12",
                    "postal_code": "38707",
                    "city": "Altenau",
                    "country_code": "DE",
                },
            },
        )
        assert order.status_code == 201, order.text
        (summary,) = (await staff_client.get("/api/v1/admin/orders")).json()["items"]
        order_id = summary["id"]
        not_allocated = (await staff_client.get(f"{INVENTORY}/orders/{order_id}/pick-list")).json()
        assert not_allocated["allocated"] is False
        assert_problem(
            await staff_client.post(f"{INVENTORY}/orders/{order_id}/allocation"),
            409,
            "order_not_allocatable",
        )
        paid = await client.post(
            f"{SHOP}/orders/{order.json()['public_token']}/payments",
            headers={"Idempotency-Key": str(uuid4())},
            json={"method": "succeeds"},
        )
        assert paid.status_code == 200, paid.text
        allocated = await staff_client.post(f"{INVENTORY}/orders/{order_id}/allocation")
        (item,) = allocated.json()["items"]
        assert (item["state"], item["location"]["code"]) == ("reserved", "R01-F01")
        await deliver()  # the handler finds the order allocated and changes nothing

        picked = await scan(staff_client, item["unit_code"], "pick", order_id=order_id)
        assert (picked["message"], picked["progress"]) == ("picked", {"picked": 1, "total": 1})
        done = (await staff_client.get(f"{INVENTORY}/orders/{order_id}/pick-list")).json()
        assert (done["complete"], done["items"][0]["state"]) == (True, "picked")
        assert_problem(
            await staff_client.get(f"{INVENTORY}/orders/{uuid4()}/pick-list"),
            404,
            "order_not_found",
        )


class TestLabels:
    @pytest.mark.parametrize("sheet", ["a4_70x37", "ql_62x29"])
    async def test_units_and_locations_as_pdf(
        self, staff_client: AsyncClient, painted: UUID, sheet: str
    ) -> None:
        await build_store(staff_client)
        created = await staff_client.post(
            f"{INVENTORY}/units", json={"variant_id": str(painted), "quantity": 2}
        )
        codes = [unit["code"] for unit in created.json()["items"]]
        response = await staff_client.post(
            f"{INVENTORY}/labels",
            json={
                "unit_codes": codes,
                "location_codes": ["R01-F01", "R01"],
                "sheet": sheet,
                "skip": 3,
            },
        )
        assert response.status_code == 200, response.text
        assert response.headers["content-type"] == "application/pdf"
        assert response.content.startswith(b"%PDF")
        assert response.headers["cache-control"] == "no-store"

    async def test_unknown_codes_and_empty_requests_are_refused(
        self, staff_client: AsyncClient
    ) -> None:
        body = assert_problem(
            await staff_client.post(
                f"{INVENTORY}/labels", json={"unit_codes": ["0000000000"], "sheet": "a4_70x37"}
            ),
            422,
            "validation_failed",
        )
        assert body["errors"][0]["field"] == "unit_codes.0"
        assert_problem(
            await staff_client.post(
                f"{INVENTORY}/labels", json={"location_codes": ["NIRGENDS"], "sheet": "ql_62x29"}
            ),
            422,
            "validation_failed",
        )
        assert_problem(
            await staff_client.post(f"{INVENTORY}/labels", json={"sheet": "a4_70x37"}),
            422,
            "validation_failed",
        )


class TestShop:
    async def test_availability_per_variant(
        self,
        client: AsyncClient,
        staff_client: AsyncClient,
        catalog: CatalogService,
        product: ProductDetails,
        painted: UUID,
    ) -> None:
        unpainted = variant_id(product, "H0", "unpainted")
        await catalog.change_variant(
            unpainted, expected_version=None, allow_backorder=True, lead_time_weeks=(2, 3)
        )
        response = await client.get(f"{SHOP}/products/{product.product.slug}/availability")
        assert response.headers["cache-control"] == "public, max-age=15"
        found = {item["variant_id"]: item for item in response.json()["items"]}
        assert found[str(painted)]["availability"] == "unavailable"
        assert (
            found[str(unpainted)]["availability"],
            found[str(unpainted)]["lead_time_min_weeks"],
            found[str(unpainted)]["lead_time_max_weeks"],
        ) == ("made_to_order", 2, 3)
        assert_problem(
            await client.get(f"{SHOP}/products/gibt-es-nicht/availability"),
            404,
            "product_not_found",
        )
        assert_problem(
            await client.put(f"{SHOP}/cart/lines/{painted}", json={"quantity": 1}),
            409,
            "insufficient_stock",
        )

    async def test_the_article_list_for_the_till(
        self, staff_client: AsyncClient, catalog: CatalogService, product: ProductDetails
    ) -> None:
        unpainted = variant_id(product, "H0", "unpainted")
        await catalog.change_variant(unpainted, expected_version=None, allow_backorder=True)
        response = await staff_client.get("/api/v1/admin/catalog/articles.csv")
        assert response.headers["content-type"] == "text/csv; charset=utf-8"
        assert response.content.startswith(b"\xef\xbb\xbf")
        rows = list(csv.reader(io.StringIO(response.content.decode("utf-8-sig")), delimiter=";"))
        assert rows[0][:5] == ["Name", "Variante", "Artikelnummer", "EAN", "Preis"]
        lines = {row[2]: row for row in rows[1:]}
        skus = {v.finish_code: v.sku for s in product.product.scales for v in s.variants}
        painted_line = lines[skus["painted"]]
        assert painted_line[1] == "H0 · Fertigmodell"
        assert painted_line[3].startswith("20")
        assert (painted_line[4], painted_line[5], painted_line[7], painted_line[8]) == (
            "49,90",
            "19",
            "vorrätig",
            "ja",
        )
        assert lines[skus["unpainted"]][7] == "auf Bestellung (1-2 Wochen)"
