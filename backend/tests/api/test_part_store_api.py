"""The parts store over HTTP: receiving, part labels, counting, assembly, and who may do what."""

from typing import Any, Final

import pytest
from httpx import AsyncClient

from modellbahn.modules.catalog.application.services import CatalogService, ProductDetails
from modellbahn.modules.media.application.services import MediaService
from tests.api.helpers import assert_problem
from tests.api.test_inventory_api import scan
from tests.api.test_manufacturing_api import BASE as MANUFACTURING
from tests.api.test_manufacturing_api import ok, part, plate, printer
from tests.conftest import Deliver
from tests.media_support import InMemoryMediaStorage
from tests.sales_support import shop_product, variant_id

INVENTORY: Final = "/api/v1/admin/inventory"
ROOF: Final = "STW-ALT-DACH-H0"
CHIMNEY: Final = "STW-ALT-SCHORNSTEIN-H0"

@pytest.fixture
async def build_store(staff_client: AsyncClient) -> None:
    """Site LAGER, shelf R01 and its compartment R01-F01."""
    for body in (
        {"segment": "LAGER", "kind": "site", "name": "Werkstatt"},
        {"parent_code": "LAGER", "segment": "R01", "kind": "shelf", "name": "Regal 1"},
        {"parent_code": "R01", "segment": "F01", "kind": "compartment"},
    ):
        response = await staff_client.post(f"{INVENTORY}/locations", json=body)
        assert response.status_code == 201, response.text


@pytest.fixture
async def product(
    catalog: CatalogService,
    media: MediaService,
    media_storage: InMemoryMediaStorage,
    deliver: Deliver,
) -> ProductDetails:
    return await shop_product(catalog, media, media_storage, deliver)


async def finished_plate(
    client: AsyncClient, deliver: Deliver, *lines: tuple[str, int, int]
) -> int:
    """A plate (part, planned, good) printed, reported done and received; its number."""
    printer_id = await printer(client, f"D{len(lines):02d}")
    job = await plate(client, printer_id, *((part_id, planned) for part_id, planned, _ in lines))
    for step in ("start", "take-off"):
        await ok(client.post(f"{MANUFACTURING}/print-jobs/{job['id']}/{step}"))
    await ok(
        client.post(
            f"{MANUFACTURING}/print-jobs/{job['id']}/complete",
            json={"lines": [{"part_id": part_id, "good": good} for part_id, _, good in lines]},
        )
    )
    await deliver()
    return int(job["number"])


@pytest.mark.usefixtures("build_store")
class TestReceiving:
    async def test_a_finished_plate_goes_from_receiving_into_a_box(
        self, staff_client: AsyncClient, deliver: Deliver
    ) -> None:
        roof = await part(staff_client, ROOF)
        number = await finished_plate(staff_client, deliver, (roof, 8, 7))

        receiving = await ok(staff_client.get(f"{INVENTORY}/receiving"))
        (receipt,) = receiving["items"]
        assert (receipt["part"]["part_number"], receipt["open"]) == (ROOF, 7)
        assert receipt["print_job"]["number"] == number

        await scan(staff_client, "R01-F01", "put_away")
        answer = await scan(staff_client, ROOF, "put_away", location_code="R01-F01")
        assert answer["message"] == "parts_stored"
        assert answer["part_effect"]["quantity"] == 7
        assert answer["location"]["part_count"] == 7
        assert (await ok(staff_client.get(f"{INVENTORY}/receiving")))["items"] == []

        stock = await ok(staff_client.get(f"{INVENTORY}/parts"))
        (line,) = stock["items"]
        assert (line["total"], line["incoming"], line["places"][0]["location_code"]) == (
            7,
            0,
            "R01-F01",
        )
        details = await ok(staff_client.get(f"{INVENTORY}/parts/{ROOF.lower()}"))
        (entry,) = details["history"]
        assert (entry["reason"], entry["print_job_number"], entry["to_location_code"]) == (
            "receive",
            number,
            "R01-F01",
        )
        tree = await ok(staff_client.get(f"{INVENTORY}/locations"))
        assert next(n for n in tree["items"] if n["code"] == "R01-F01")["part_count"] == 7
        contents = await ok(staff_client.get(f"{INVENTORY}/locations/R01-F01"))
        assert [(p["part"]["part_number"], p["quantity"]) for p in contents["parts"]] == [(ROOF, 7)]

    async def test_writing_off_and_counting_are_for_owner_and_staff(
        self, staff_client: AsyncClient, packer_client: AsyncClient, deliver: Deliver
    ) -> None:
        roof = await part(staff_client, ROOF)
        await finished_plate(staff_client, deliver, (roof, 4, 4))
        (receipt,) = (await ok(packer_client.get(f"{INVENTORY}/receiving")))["items"]
        write_off = f"{INVENTORY}/receiving/{receipt['id']}/write-off"
        count = f"{INVENTORY}/parts/{ROOF}/count"

        assert_problem(await packer_client.post(write_off, json={}), 403, "insufficient_role")
        assert_problem(
            await packer_client.post(count, json={"location_code": "R01-F01", "quantity": 1}),
            403,
            "insufficient_role",
        )
        written = await ok(staff_client.post(write_off, json={"note": "zerbrochen"}))
        assert (written["open"], written["written_off"]) == (0, 4)
        assert_problem(await staff_client.post(write_off, json={}), 409, "invalid_receipt_state")
        counted = await ok(
            staff_client.post(count, json={"location_code": "r01-f01", "quantity": 5, "note": ""})
        )
        assert counted["stock"]["total"] == 5
        assert_problem(
            await staff_client.post(
                f"{INVENTORY}/parts/STW-GIBT-ES-NICHT/count",
                json={"location_code": "R01-F01", "quantity": 1},
            ),
            404,
            "part_not_found",
        )
        assert_problem(
            await staff_client.post(
                f"{INVENTORY}/receiving/0192f1c4-0000-7000-8000-000000000001/write-off", json={}
            ),
            404,
            "receipt_not_found",
        )

    async def test_part_labels(self, packer_client: AsyncClient, staff_client: AsyncClient) -> None:
        await part(staff_client, ROOF)
        response = await packer_client.post(
            f"{INVENTORY}/labels", json={"part_numbers": [ROOF], "sheet": "ql_62x29"}
        )
        assert response.status_code == 200, response.text
        assert response.content.startswith(b"%PDF")


@pytest.mark.usefixtures("build_store")
class TestAssembly:
    async def test_kits_are_assembled_from_the_boxes_by_their_bill_of_materials(
        self,
        staff_client: AsyncClient,
        packer_client: AsyncClient,
        product: ProductDetails,
    ) -> None:
        roof, chimney = await part(staff_client, ROOF), await part(staff_client, CHIMNEY)
        (scale,) = product.product.scales
        await ok(
            staff_client.put(
                f"{MANUFACTURING}/product-scales/{scale.id}/bom",
                json={
                    "lines": [{"part_id": roof, "quantity": 1}, {"part_id": chimney, "quantity": 2}]
                },
            )
        )
        for number, quantity in ((ROOF, 2), (CHIMNEY, 3)):
            await ok(
                staff_client.post(
                    f"{INVENTORY}/parts/{number}/count",
                    json={"location_code": "R01-F01", "quantity": quantity},
                )
            )
        painted = str(variant_id(product, "H0", "painted"))

        plan = await ok(
            packer_client.get(
                f"{INVENTORY}/assembly-plan", params={"variant_id": painted, "quantity": 2}
            )
        )
        assert (plan["ready"], plan["possible"]) == (False, 1)
        assert [(p["part"]["part_number"], p["missing"]) for p in plan["parts"]] == [
            (ROOF, 0),
            (CHIMNEY, 1),
        ]

        body = {"variant_id": painted, "quantity": 1, "location_code": "R01-F01"}
        assert_problem(
            await packer_client.post(f"{INVENTORY}/assemblies", json=body), 403, "insufficient_role"
        )
        response = await staff_client.post(f"{INVENTORY}/assemblies", json=body)
        assert response.status_code == 201, response.text
        assembled: dict[str, Any] = response.json()
        (unit,) = assembled["units"]
        assert unit["status"] == "in_stock"
        details = await ok(staff_client.get(f"{INVENTORY}/units/{unit['code']}"))
        assert sorted((p["part"]["part_number"], p["quantity"]) for p in details["parts"]) == [
            (ROOF, 1),
            (CHIMNEY, 2),
        ]
        assert_problem(
            await staff_client.post(f"{INVENTORY}/assemblies", json=body), 409, "parts_missing"
        )

    async def test_a_product_without_a_bill_of_materials(
        self, staff_client: AsyncClient, product: ProductDetails
    ) -> None:
        painted = str(variant_id(product, "H0", "painted"))
        assert_problem(
            await staff_client.get(
                f"{INVENTORY}/assembly-plan", params={"variant_id": painted, "quantity": 1}
            ),
            409,
            "no_bill_of_materials",
        )
        assert_problem(
            await staff_client.get(
                f"{INVENTORY}/assembly-plan",
                params={"variant_id": "0192f1c4-0000-7000-8000-000000000001", "quantity": 1},
            ),
            404,
            "variant_not_found",
        )
        assert_problem(
            await staff_client.get(
                f"{INVENTORY}/assembly-plan", params={"variant_id": painted, "quantity": 51}
            ),
            422,
            "validation_failed",
        )
