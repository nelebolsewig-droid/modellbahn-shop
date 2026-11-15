"""Stock by quantity through the API (ADR 0028): a shelf in one step, what lies where,
moving, taking out and counting by number; who may and how refusals look."""

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


async def book_in(staff: AsyncClient, variant: UUID, quantity: int, code: str) -> None:
    response = await staff.post(
        f"{INVENTORY}/units",
        json={"variant_id": str(variant), "quantity": quantity, "location_code": code},
    )
    assert response.status_code == 201, response.text


async def places(client: AsyncClient, **params: str) -> list[dict[str, Any]]:
    response = await client.get(f"{INVENTORY}/stock/places", params=params)
    assert response.status_code == 200, response.text
    items: list[dict[str, Any]] = response.json()["items"]
    return items


class TestShelves:
    async def test_one_step_and_only_owner_and_staff(
        self, staff_client: AsyncClient, packer_client: AsyncClient
    ) -> None:
        assert_problem(
            await packer_client.post(f"{INVENTORY}/locations/shelves", json={"levels": 2}),
            403,
            "insufficient_role",
        )
        created = await staff_client.post(
            f"{INVENTORY}/locations/shelves", json={"name": "Regal 1", "levels": 2}
        )
        assert created.status_code == 201, created.text
        body = created.json()
        assert body["shelf"]["code"] == "R01"
        assert [level["code"] for level in body["levels"]] == ["R01-B01", "R01-B02"]
        tree = (await staff_client.get(f"{INVENTORY}/locations")).json()["items"]
        by_code = {node["code"]: node for node in tree}
        assert (by_code["R01"]["holds_goods"], by_code["R01-B02"]["holds_goods"]) == (False, True)
        assert by_code["R01-B02"]["place"] == "Regal 1, Boden 2"
        assert_problem(
            await staff_client.post(f"{INVENTORY}/locations/shelves", json={"levels": 21}),
            422,
            "validation_failed",
        )


class TestStockByQuantity:
    async def test_where_it_lies_move_take_out_count_and_history(
        self,
        staff_client: AsyncClient,
        packer_client: AsyncClient,
        product: ProductDetails,
        painted: UUID,
    ) -> None:
        await staff_client.post(
            f"{INVENTORY}/locations/shelves", json={"name": "Regal 1", "levels": 2}
        )
        await book_in(staff_client, painted, 5, "R01-B01")
        # Packers see what lies where, but book nothing by number.
        (line,) = await places(packer_client, product_id=str(product.product.id))
        assert (line["place"], line["free"], line["reserved"]) == ("Regal 1, Boden 1", 5, 0)
        move = {"variant_id": str(painted), "from_location": "R01-B01", "to_location": "R01-B02"}
        assert_problem(
            await packer_client.post(f"{INVENTORY}/stock/moves", json={**move, "quantity": 1}),
            403,
            "insufficient_role",
        )

        moved = await staff_client.post(f"{INVENTORY}/stock/moves", json={**move, "quantity": 2})
        assert moved.json()["moved"] == 2, moved.text
        too_many = assert_problem(
            await staff_client.post(f"{INVENTORY}/stock/moves", json={**move, "quantity": 9}),
            409,
            "not_enough_pieces",
        )
        assert "only 3" in too_many["detail"]
        out = await staff_client.post(
            f"{INVENTORY}/stock/scraps",
            json={
                "variant_id": str(painted),
                "location_code": "R01-B02",
                "quantity": 1,
                "reason": "sold",
            },
        )
        assert out.json()["sources"] == [
            {"code": "R01-B02", "place": "Regal 1, Boden 2", "quantity": 1}
        ]
        assert_problem(
            await staff_client.post(
                f"{INVENTORY}/stock/scraps",
                json={"variant_id": str(painted), "quantity": 9, "reason": "sold"},
            ),
            409,
            "not_enough_free",
        )
        counted = await staff_client.post(
            f"{INVENTORY}/stock/counts",
            json={
                "lines": [
                    {
                        "variant_id": str(painted),
                        "location_code": "R01-B01",
                        "expected": 3,
                        "counted": 5,
                    }
                ]
            },
        )
        assert counted.json() == {"missing": 0, "added": 2, "reserved": 0}, counted.text
        outdated = assert_problem(
            await staff_client.post(
                f"{INVENTORY}/stock/counts",
                json={
                    "lines": [
                        {
                            "variant_id": str(painted),
                            "location_code": "R01-B01",
                            "expected": 3,
                            "counted": 1,
                        }
                    ]
                },
            ),
            409,
            "stocktake_outdated",
        )
        assert "R01-B01" in outdated["detail"]

        products = (await staff_client.get(f"{INVENTORY}/stock/products")).json()["items"]
        assert [(p["free"], [pl["quantity"] for pl in p["places"]]) for p in products] == [
            (6, [5, 1])
        ]
        history = await staff_client.get(
            f"{INVENTORY}/stock/history", params={"product_id": str(product.product.id)}
        )
        reasons = [(row["reason"], row["quantity"]) for row in history.json()["items"]]
        assert reasons[:3] == [("put_away", 2), ("label", 2), ("scrap", 1)]
        assert_problem(
            await staff_client.get(
                f"{INVENTORY}/stock/history", params={"product_id": str(uuid4())}
            ),
            404,
            "product_not_found",
        )
