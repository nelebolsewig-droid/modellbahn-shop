"""Putting the books right through the API: booking in again, correcting the variant,
counting a location; who may do it and how refusals look."""

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
def unpainted(product: ProductDetails) -> UUID:
    return variant_id(product, "H0", "unpainted")


async def build_store(staff: AsyncClient) -> None:
    for body in (
        {"segment": "LAGER", "kind": "site"},
        {"parent_code": "LAGER", "segment": "R01", "kind": "shelf"},
        {"parent_code": "R01", "segment": "F01", "kind": "compartment"},
        {"parent_code": "R01", "segment": "F02", "kind": "compartment"},
    ):
        response = await staff.post(f"{INVENTORY}/locations", json=body)
        assert response.status_code == 201, response.text


async def label(
    staff: AsyncClient, variant: UUID, quantity: int, location: str | None = None
) -> list[dict[str, Any]]:
    created = await staff.post(
        f"{INVENTORY}/units",
        json={"variant_id": str(variant), "quantity": quantity, "location_code": location},
    )
    assert created.status_code == 201, created.text
    items: list[dict[str, Any]] = created.json()["items"]
    return items


class TestBookingInAgain:
    async def test_scrapped_pieces_come_back_and_only_owner_and_staff_may(
        self,
        staff_client: AsyncClient,
        packer_client: AsyncClient,
        client: AsyncClient,
        painted: UUID,
    ) -> None:
        await build_store(staff_client)
        gone, kept = await label(staff_client, painted, 2, "R01-F01")
        scrapped = await staff_client.post(
            f"{INVENTORY}/units/scraps",
            json={"unit_ids": [gone["id"]], "reason": "missing", "note": "Inventur"},
        )
        assert scrapped.status_code == 200, scrapped.text
        body = {"unit_ids": [gone["id"]], "location_code": "r01-f02"}

        assert_problem(
            await packer_client.post(f"{INVENTORY}/units/restores", json=body),
            403,
            "insufficient_role",
        )
        assert_problem(
            await client.post(f"{INVENTORY}/units/restores", json=body), 401, "not_authenticated"
        )
        restored = await staff_client.post(f"{INVENTORY}/units/restores", json=body)
        assert restored.status_code == 200, restored.text
        assert restored.json() | {"location": None} == {
            "restored": 1,
            "already_there": 0,
            "reserved": 0,
            "location": None,
        }
        assert restored.json()["location"]["code"] == "R01-F02"
        details = (await staff_client.get(f"{INVENTORY}/units/{gone['code']}")).json()
        assert (details["status"], details["scrap_reason"], details["scrap_note"]) == (
            "in_stock",
            None,
            "",
        )
        assert details["history"][-1]["reason"] == "restore"
        assert details["history"][-1]["to_location_code"] == "R01-F02"

        refused = assert_problem(
            await staff_client.post(
                f"{INVENTORY}/units/restores",
                json={"unit_ids": [gone["id"], kept["id"]], "location_code": "R01-F02"},
            ),
            409,
            "units_not_restorable",
        )
        # The piece booked in already is left alone; the one never scrapped is named.
        assert kept["code"] in refused["detail"]
        assert gone["code"] not in refused["detail"]
        assert_problem(
            await staff_client.post(
                f"{INVENTORY}/units/restores",
                json={"unit_ids": [gone["id"]], "location_code": "R77"},
            ),
            404,
            "location_not_found",
        )
        assert_problem(
            await staff_client.post(
                f"{INVENTORY}/units/restores", json={"unit_ids": [], "location_code": "R01-F01"}
            ),
            422,
            "validation_failed",
        )


class TestCorrectingTheVariant:
    async def test_a_free_piece_becomes_another_variant(
        self,
        staff_client: AsyncClient,
        packer_client: AsyncClient,
        painted: UUID,
        unpainted: UUID,
    ) -> None:
        await build_store(staff_client)
        (piece,) = await label(staff_client, painted, 1, "R01-F01")
        url = f"{INVENTORY}/units/{piece['code']}/correction"

        assert_problem(
            await packer_client.post(url, json={"variant_id": str(unpainted)}),
            403,
            "insufficient_role",
        )
        corrected = await staff_client.post(url, json={"variant_id": str(unpainted)})
        assert corrected.status_code == 200, corrected.text
        unit = corrected.json()
        assert (unit["variant_id"], unit["variant"]["variant_id"], unit["status"]) == (
            str(unpainted),
            str(unpainted),
            "in_stock",
        )
        assert unit["variant"]["gtin"] != piece["variant"]["gtin"]
        assert unit["location"]["code"] == "R01-F01"
        history = (await staff_client.get(f"{INVENTORY}/units/{piece['code']}")).json()["history"]
        last = history[-1]
        assert (last["reason"], last["from_variant"]["sku"], last["to_variant"]["sku"]) == (
            "correct",
            piece["variant"]["sku"],
            unit["variant"]["sku"],
        )
        assert history[0]["from_variant"] is None
        stock = {
            s["variant_id"]: s["in_stock"]
            for s in (await staff_client.get(f"{INVENTORY}/stock")).json()["items"]
        }
        assert stock == {str(unpainted): 1}

        assert_problem(
            await staff_client.post(url, json={"variant_id": str(unpainted)}),
            422,
            "validation_failed",
        )
        assert_problem(
            await staff_client.post(url, json={"variant_id": str(uuid4())}),
            404,
            "variant_not_found",
        )
        assert_problem(
            await staff_client.post(
                f"{INVENTORY}/units/0000000000/correction", json={"variant_id": str(painted)}
            ),
            404,
            "unit_not_found",
        )
        await staff_client.post(
            f"{INVENTORY}/units/{piece['code']}/scrap", json={"reason": "mistake"}
        )
        refused = assert_problem(
            await staff_client.post(url, json={"variant_id": str(painted)}),
            409,
            "unit_not_correctable",
        )
        assert "scrapped" in refused["detail"]


class TestStocktake:
    async def test_count_a_place_missing_out_found_in(
        self,
        staff_client: AsyncClient,
        packer_client: AsyncClient,
        client: AsyncClient,
        painted: UUID,
    ) -> None:
        await build_store(staff_client)
        present, lost = await label(staff_client, painted, 2, "R01-F01")
        (stray,) = await label(staff_client, painted, 1, "R01-F02")
        (unbooked,) = await label(staff_client, painted, 1)
        url = f"{INVENTORY}/locations/r01-f01/stocktakes"
        body = {
            "present_unit_ids": [present["id"]],
            "missing_unit_ids": [lost["id"]],
            "found_unit_ids": [stray["id"], unbooked["id"]],
        }

        assert_problem(await packer_client.post(url, json=body), 403, "insufficient_role")
        assert_problem(await client.post(url, json=body), 401, "not_authenticated")
        counted = await staff_client.post(url, json=body)
        assert counted.status_code == 200, counted.text
        assert counted.json() | {"location": None} == {
            "confirmed": 1,
            "scrapped": 1,
            "found": 2,
            "reserved": 0,
            "location": None,
        }
        inside = (await staff_client.get(f"{INVENTORY}/locations/R01-F01")).json()["units"]
        assert {u["code"] for u in inside} == {present["code"], stray["code"], unbooked["code"]}
        missing = (await staff_client.get(f"{INVENTORY}/units/{lost['code']}")).json()
        assert (missing["status"], missing["scrap_reason"]) == ("scrapped", "missing")

        # The answer got lost and the request comes again: nothing more is booked.
        again = await staff_client.post(url, json=body)
        assert (again.json()["scrapped"], again.json()["found"]) == (0, 0)

    async def test_refusals(self, staff_client: AsyncClient, painted: UUID) -> None:
        await build_store(staff_client)
        (counted,) = await label(staff_client, painted, 1, "R01-F01")
        (late,) = await label(staff_client, painted, 1, "R01-F01")
        url = f"{INVENTORY}/locations/R01-F01/stocktakes"

        outdated = assert_problem(
            await staff_client.post(url, json={"present_unit_ids": [counted["id"]]}),
            409,
            "stocktake_outdated",
        )
        assert late["code"] in outdated["detail"]
        assert_problem(
            await staff_client.post(
                url,
                json={
                    "present_unit_ids": [counted["id"], late["id"]],
                    "found_unit_ids": [str(uuid4())],
                },
            ),
            409,
            "units_not_movable",
        )
        assert_problem(
            await staff_client.post(
                url,
                json={"present_unit_ids": [counted["id"]], "missing_unit_ids": [counted["id"]]},
            ),
            422,
            "validation_failed",
        )
        assert_problem(
            await staff_client.post(f"{INVENTORY}/locations/R01/stocktakes", json={}),
            422,
            "validation_failed",
        )
        assert_problem(
            await staff_client.post(f"{INVENTORY}/locations/R77/stocktakes", json={}),
            404,
            "location_not_found",
        )
