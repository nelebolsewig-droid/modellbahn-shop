"""One code per model through the API (ADR 0027): put away and book out with a quantity,
who may book out, how refusals look, and undoing."""

from typing import Any
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient

from modellbahn.modules.catalog.application.services import CatalogService, ProductDetails
from modellbahn.modules.media.application.services import MediaService
from tests.api.helpers import assert_problem
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


@pytest.fixture
def gtin(product: ProductDetails, painted: UUID) -> str:
    return next(v.gtin for s in product.product.scales for v in s.variants if v.id == painted)


@pytest.fixture
async def shelf(staff_client: AsyncClient) -> None:
    for body in (
        {"segment": "LAGER", "kind": "site"},
        {"parent_code": "LAGER", "segment": "R01", "kind": "shelf"},
        {"parent_code": "R01", "segment": "F01", "kind": "compartment"},
        {"parent_code": "R01", "segment": "F02", "kind": "compartment"},
    ):
        response = await staff_client.post(f"{INVENTORY}/locations", json=body)
        assert response.status_code == 201, response.text


def body(raw: str, mode: str, *, quantity: int = 1, **context: str) -> dict[str, Any]:
    return {
        "scan_id": str(uuid4()),
        "raw": raw,
        "mode": mode,
        "source": "scanner",
        "context": context,
        "quantity": quantity,
    }


async def scan(client: AsyncClient, request: dict[str, Any]) -> dict[str, Any]:
    response = await client.post(f"{INVENTORY}/scans", json=request)
    assert response.status_code == 200, response.text
    answer: dict[str, Any] = response.json()
    return answer


async def stock_of(client: AsyncClient, variant: UUID) -> tuple[int, int]:
    """``(labeled, in_stock)`` of the variant."""
    items = (await client.get(f"{INVENTORY}/stock")).json()["items"]
    line = next((item for item in items if item["variant_id"] == str(variant)), None)
    return (line["labeled"], line["in_stock"]) if line else (0, 0)


class TestPuttingAway:
    async def test_seven_pieces_with_one_label_and_back(
        self, packer_client: AsyncClient, shelf: None, painted: UUID, gtin: str
    ) -> None:
        # Packers put away, as before; a model's label books as many as they say.
        answer = await scan(
            packer_client, body(gtin, "put_away", quantity=7, location_code="R01-F01")
        )
        assert (answer["outcome"], answer["message"], answer["quantity"]) == (
            "applied",
            "booked_in",
            7,
        )
        assert answer["stock_effect"] | {"reserved_for": None} == {
            "quantity": 7,
            "location": "R01-F01",
            "in_location": 7,
            "stored": 0,
            "created": 7,
            "reserved": 0,
            "reserved_for": None,
            "reason": None,
            "from_locations": [],
        }
        assert (answer["variant"]["free_units"], answer["variant"]["free_here"]) == (7, 7)
        assert answer["resolved"] == {"kind": "variant", "code": gtin}
        assert await stock_of(packer_client, painted) == (0, 7)

        undone = await packer_client.post(f"{INVENTORY}/scans/{answer['scan_id']}/undo")
        assert undone.status_code == 200, undone.text
        assert undone.json()["undone"] is True
        assert await stock_of(packer_client, painted) == (0, 0)
        out = await packer_client.get(
            f"{INVENTORY}/units", params={"variant_id": str(painted), "status": "scrapped"}
        )
        assert {u["scrap_reason"] for u in out.json()["items"]} == {"mistake"}

    @pytest.mark.parametrize(
        ("change", "field"),
        [
            ({"quantity": 0}, "quantity"),
            ({"quantity": 201}, "quantity"),
            ({"context": {"reason": "verschenkt"}}, "context.reason"),
        ],
    )
    async def test_refusals(
        self, staff_client: AsyncClient, gtin: str, change: dict[str, Any], field: str
    ) -> None:
        refused = assert_problem(
            await staff_client.post(f"{INVENTORY}/scans", json=body(gtin, "scrap") | change),
            422,
            "validation_failed",
        )
        assert refused["errors"][0]["field"] == field


class TestBookingOut:
    async def test_sold_at_the_fair_by_scan(
        self, staff_client: AsyncClient, shelf: None, painted: UUID, gtin: str
    ) -> None:
        booked = await staff_client.post(
            f"{INVENTORY}/units",
            json={"variant_id": str(painted), "quantity": 5, "location_code": "R01-F02"},
        )
        assert booked.status_code == 201, booked.text

        sold = await scan(staff_client, body(gtin, "scrap", quantity=3))

        assert (sold["outcome"], sold["message"]) == ("applied", "booked_out")
        assert sold["stock_effect"]["reason"] == "sold"
        assert sold["stock_effect"]["from_locations"] == [{"code": "R01-F02", "quantity": 3}]
        assert sold["variant"]["free_units"] == 2
        assert sold["undoable"] is True
        too_many = await scan(
            staff_client, body(gtin, "scrap", quantity=3, location_code="R01-F02", reason="damaged")
        )
        assert (too_many["outcome"], too_many["message"]) == ("rejected", "not_enough_free")
        assert (too_many["variant"]["free_units"], too_many["variant"]["free_here"]) == (2, 2)
        assert too_many["stock_effect"] is None
        assert await stock_of(staff_client, painted) == (0, 2)

        undone = await staff_client.post(f"{INVENTORY}/scans/{sold['scan_id']}/undo")
        assert undone.json()["undone"] is True
        assert await stock_of(staff_client, painted) == (0, 5)

    async def test_only_owner_and_staff_book_out(
        self,
        packer_client: AsyncClient,
        client: AsyncClient,
        staff_client: AsyncClient,
        shelf: None,
        painted: UUID,
        gtin: str,
    ) -> None:
        await staff_client.post(
            f"{INVENTORY}/units",
            json={"variant_id": str(painted), "quantity": 1, "location_code": "R01-F01"},
        )
        assert_problem(
            await packer_client.post(f"{INVENTORY}/scans", json=body(gtin, "scrap")),
            403,
            "insufficient_role",
        )
        assert_problem(
            await client.post(f"{INVENTORY}/scans", json=body(gtin, "scrap")),
            401,
            "not_authenticated",
        )
        assert await stock_of(staff_client, painted) == (0, 1)
        # Choosing the place to book out of is a scan in that mode too.
        chosen = await scan(staff_client, body("R01-F01", "scrap"))
        assert (chosen["outcome"], chosen["location"]["code"]) == ("selected", "R01-F01")
