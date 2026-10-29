"""The manufacturing API: the printer hall, parts and kits, plates from queue to done."""

from typing import Any, Final

from httpx import AsyncClient

from tests.api.helpers import PRODUCTS, assert_problem

BASE: Final = "/api/v1/admin/manufacturing"


async def created(client: AsyncClient, path: str, body: dict[str, Any]) -> dict[str, Any]:
    response = await client.post(f"{BASE}{path}", json=body)
    assert response.status_code == 201, response.text
    result: dict[str, Any] = response.json()
    return result


async def ok(response_coroutine: Any) -> dict[str, Any]:
    response = await response_coroutine
    assert response.status_code == 200, response.text
    result: dict[str, Any] = response.json()
    return result


async def printer(client: AsyncClient, code: str = "D01", technology: str = "resin") -> str:
    body = await created(
        client,
        "/printers",
        {
            "code": code,
            "name": "Saturn links",
            "model": "Elegoo Saturn 4 Ultra",
            "technology": technology,
            "build_x_mm": 218,
            "build_y_mm": 123,
            "build_z_mm": 220,
        },
    )
    return str(body["id"])


async def part(
    client: AsyncClient, number: str = "STW-ALT-DACH-H0", *, scale: str = "H0", minutes: int = 190
) -> str:
    body = await created(
        client,
        "/parts",
        {
            "part_number": number,
            "name": f"Teil {number}",
            "scale_code": scale,
            "technology": "resin",
            "plate_minutes": minutes,
            "parts_per_plate": 4,
        },
    )
    return str(body["id"])


async def plate(client: AsyncClient, printer_id: str, *lines: tuple[str, int]) -> dict[str, Any]:
    return await created(
        client,
        "/print-jobs",
        {
            "printer_id": printer_id,
            "lines": [{"part_id": part_id, "quantity": quantity} for part_id, quantity in lines],
        },
    )


class TestPrinters:
    async def test_the_hall_shows_each_printer_with_its_state(
        self, staff_client: AsyncClient
    ) -> None:
        printer_id = await printer(staff_client, "D02")
        await printer(staff_client, "D01")

        hall = await ok(staff_client.get(f"{BASE}/hall"))
        assert [entry["code"] for entry in hall["printers"]] == ["D01", "D02"]
        assert hall["counts"] == {
            "in_service": 2,
            "defective": 0,
            "in_repair": 0,
            "retired": 0,
            "printing": 0,
            "queued": 0,
            "post_processing": 0,
        }
        reported = await ok(
            staff_client.post(
                f"{BASE}/printers/{printer_id}/status",
                json={"status": "defective", "note": "Düse verstopft"},
            )
        )
        assert (reported["status"], reported["status_note"]) == ("defective", "Düse verstopft")
        record = await ok(staff_client.get(f"{BASE}/printers/{printer_id}"))
        assert [entry["to_status"] for entry in record["history"]] == ["defective", "in_service"]
        assert record["history"][0]["staff_name"] == "Chefin"
        hall = await ok(staff_client.get(f"{BASE}/hall"))
        assert hall["counts"]["defective"] == 1

    async def test_details_are_checked(self, staff_client: AsyncClient) -> None:
        await printer(staff_client, "D01")
        duplicate = await staff_client.post(
            f"{BASE}/printers", json={"code": "d01", "technology": "resin"}
        )
        body = assert_problem(duplicate, 422, "validation_failed")
        assert body["errors"][0]["field"] == "code"
        half = await staff_client.post(
            f"{BASE}/printers", json={"code": "D02", "technology": "fdm", "build_x_mm": 200}
        )
        assert_problem(half, 422, "validation_failed")

    async def test_packers_report_and_watch_but_do_not_set_up(
        self, staff_client: AsyncClient, packer_client: AsyncClient
    ) -> None:
        printer_id = await printer(staff_client)
        assert (await packer_client.get(f"{BASE}/hall")).status_code == 200
        response = await packer_client.post(
            f"{BASE}/printers/{printer_id}/status", json={"status": "in_repair"}
        )
        assert response.status_code == 200, response.text
        assert_problem(
            await packer_client.post(f"{BASE}/printers", json={"code": "D9", "technology": "fdm"}),
            403,
            "insufficient_role",
        )
        assert_problem(
            await packer_client.post(f"{BASE}/print-jobs", json={"printer_id": printer_id}),
            403,
            "insufficient_role",
        )

    async def test_a_printer_with_plates_cannot_be_removed(self, staff_client: AsyncClient) -> None:
        printer_id = await printer(staff_client)
        await plate(staff_client, printer_id, (await part(staff_client), 1))
        assert_problem(
            await staff_client.delete(f"{BASE}/printers/{printer_id}"), 409, "printer_in_use"
        )
        assert_problem(
            await staff_client.post(
                f"{BASE}/printers/{printer_id}/status", json={"status": "retired"}
            ),
            409,
            "printer_has_queue",
        )
        spare = await printer(staff_client, "D02")
        assert (await staff_client.delete(f"{BASE}/printers/{spare}")).status_code == 204


class TestPartsAndKits:
    async def test_materials_and_parts(self, staff_client: AsyncClient) -> None:
        material = await created(
            staff_client, "/materials", {"name": "Resin grau", "technology": "resin"}
        )
        body = await created(
            staff_client,
            "/parts",
            {
                "part_number": "stw-alt-dach-h0",
                "name": "Dach",
                "scale_code": "H0",
                "technology": "resin",
                "material_id": material["id"],
                "layer_height_um": 50,
                "plate_minutes": 180,
                "parts_per_plate": 8,
                "material_per_part": 3.456,
            },
        )
        assert body["part_number"] == "STW-ALT-DACH-H0"
        assert body["material"] == {"id": material["id"], "name": "Resin grau"}
        assert (body["minutes_per_part"], body["material_per_part"]) == (22.5, 3.46)

        listed = await ok(staff_client.get(f"{BASE}/parts", params={"scale": "H0", "q": "dach"}))
        assert [item["part_number"] for item in listed["items"]] == ["STW-ALT-DACH-H0"]
        materials = await ok(staff_client.get(f"{BASE}/materials"))
        assert materials["items"][0]["part_count"] == 1
        assert_problem(
            await staff_client.delete(f"{BASE}/materials/{material['id']}"),
            409,
            "material_in_use",
        )

    async def test_a_kit_and_its_parts(self, staff_client: AsyncClient) -> None:
        product = (await staff_client.post(PRODUCTS, json={"name": "Stellwerk Altenau"})).json()
        response = await staff_client.post(
            f"{PRODUCTS}/{product['id']}/scales", json={"scale_code": "H0"}
        )
        assert response.status_code == 201, response.text
        product_scale_id = response.json()["scales"][0]["id"]
        bom_path = f"{BASE}/product-scales/{product_scale_id}/bom"

        empty = await ok(staff_client.get(bom_path))
        assert (empty["lines"], empty["part_count"], empty["updated_at"]) == ([], 0, None)
        assert empty["product_scale"]["product_name"] == "Stellwerk Altenau"

        body_id = await part(staff_client, "BODY", minutes=240)
        roof_id = await part(staff_client, "DACH", minutes=60)
        n_roof = await part(staff_client, "DACH-N", scale="N")
        bom = await ok(
            staff_client.put(
                bom_path,
                json={
                    "lines": [
                        {"part_id": body_id, "quantity": 1},
                        {"part_id": roof_id, "quantity": 2},
                    ]
                },
            )
        )
        assert [(line["part"]["part_number"], line["quantity"]) for line in bom["lines"]] == [
            ("BODY", 1),
            ("DACH", 2),
        ]
        # A body is a quarter of a 240-minute plate, a roof a quarter of 60 minutes.
        assert (bom["part_count"], bom["print_minutes"]) == (3, 90)

        wrong = await staff_client.put(
            bom_path, json={"lines": [{"part_id": n_roof, "quantity": 1}]}
        )
        body = assert_problem(wrong, 422, "validation_failed")
        assert body["errors"][0] == {
            "field": "lines.0.part_id",
            "code": "wrong_scale",
            "message": "not a part for H0",
        }
        assert_problem(
            await staff_client.delete(f"/api/v1/admin/product-scales/{product_scale_id}"),
            409,
            "product_scale_has_bom",
        )
        assert_problem(await staff_client.delete(f"{BASE}/parts/{roof_id}"), 409, "part_in_use")
        record = await ok(staff_client.get(f"{BASE}/parts/{roof_id}"))
        assert record["uses"][0]["quantity"] == 2
        cleared = await ok(staff_client.put(bom_path, json={"lines": []}))
        assert cleared["lines"] == []

    async def test_an_unknown_product_scale(self, staff_client: AsyncClient) -> None:
        missing = await staff_client.get(
            f"{BASE}/product-scales/0192f1c4-0000-7000-8000-000000000001/bom"
        )
        assert_problem(missing, 404, "product_scale_not_found")


class TestPrintJobs:
    async def test_from_the_queue_to_done(
        self, staff_client: AsyncClient, packer_client: AsyncClient
    ) -> None:
        printer_id = await printer(staff_client)
        roof = await part(staff_client, "DACH", minutes=190)
        first = await plate(staff_client, printer_id, (roof, 4))
        second = await plate(staff_client, printer_id, (roof, 2))
        assert (first["status"], first["planned_minutes"], first["part_count"]) == (
            "queued",
            190,
            4,
        )
        assert first["printer"]["code"] == "D01"

        started = await ok(packer_client.post(f"{BASE}/print-jobs/{first['id']}/start"))
        assert started["status"] == "printing"
        assert started["expected_end_at"] is not None
        assert_problem(
            await packer_client.post(f"{BASE}/print-jobs/{second['id']}/start"),
            409,
            "printer_busy",
        )
        hall = await ok(staff_client.get(f"{BASE}/hall"))
        desk = hall["printers"][0]
        assert desk["printing"]["id"] == first["id"]
        assert [job["id"] for job in desk["queue"]] == [second["id"]]

        await ok(packer_client.post(f"{BASE}/print-jobs/{first['id']}/take-off"))
        done = await ok(
            packer_client.post(
                f"{BASE}/print-jobs/{first['id']}/complete",
                json={"lines": [{"part_id": roof, "good": 3}]},
            )
        )
        assert done["status"] == "done"
        assert (done["lines"][0]["good"], done["lines"][0]["failed"]) == (3, 1)
        assert_problem(
            await packer_client.post(f"{BASE}/print-jobs/{first['id']}/fail", json={}),
            409,
            "invalid_print_job_state",
        )

        listed = await ok(staff_client.get(f"{BASE}/print-jobs", params={"status": "done"}))
        assert [job["id"] for job in listed["items"]] == [first["id"]]
        cancelled = await ok(staff_client.post(f"{BASE}/print-jobs/{second['id']}/cancel"))
        assert cancelled["status"] == "cancelled"

    async def test_a_waiting_plate_moves_and_a_defective_printer_starts_nothing(
        self, staff_client: AsyncClient
    ) -> None:
        first = await printer(staff_client, "D01")
        second = await printer(staff_client, "D02")
        job = await plate(staff_client, first, (await part(staff_client), 1))
        moved = await ok(
            staff_client.put(
                f"{BASE}/print-jobs/{job['id']}",
                json={"printer_id": second, "planned_minutes": 45, "note": "eilig"},
            )
        )
        assert (moved["printer"]["code"], moved["planned_minutes"]) == ("D02", 45)
        await ok(
            staff_client.post(f"{BASE}/printers/{second}/status", json={"status": "defective"})
        )
        assert_problem(
            await staff_client.post(f"{BASE}/print-jobs/{job['id']}/start"),
            409,
            "printer_not_in_service",
        )

    async def test_a_plate_needs_parts(self, staff_client: AsyncClient) -> None:
        printer_id = await printer(staff_client)
        empty = await staff_client.post(
            f"{BASE}/print-jobs", json={"printer_id": printer_id, "lines": []}
        )
        assert_problem(empty, 422, "validation_failed")
        missing = await staff_client.get(f"{BASE}/print-jobs/0192f1c4-0000-7000-8000-000000000001")
        assert_problem(missing, 404, "print_job_not_found")
