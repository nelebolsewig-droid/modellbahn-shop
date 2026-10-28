"""The catalogue API: editing with ETag and If-Match, publishing, and the shop's routes."""

from typing import Any
from uuid import uuid4

import pytest
from httpx import AsyncClient, Response

from modellbahn.modules.media.application.services import MediaService
from tests.api.helpers import CATEGORIES, PRODUCTS, SHOP, assert_problem
from tests.conftest import Deliver
from tests.media_support import InMemoryMediaStorage, photo, ready_image


def etag(response: Response) -> str:
    value = response.headers["etag"]
    assert value == f'"{response.json()["version"]}"'
    return value


async def create(staff_client: AsyncClient, name: str = "Stellwerk Altenau") -> Response:
    response = await staff_client.post(PRODUCTS, json={"name": name})
    assert response.status_code == 201, response.text
    return response


async def publishable(
    staff_client: AsyncClient,
    media: MediaService,
    media_storage: InMemoryMediaStorage,
    deliver: Deliver,
) -> dict[str, Any]:
    """Create a product through the API that satisfies every rule of the shop."""
    category = (await staff_client.post(CATEGORIES, json={"name": "Stellwerke"})).json()
    product = (await create(staff_client)).json()
    product_id = product["id"]
    response = await staff_client.patch(
        f"{PRODUCTS}/{product_id}",
        json={
            "summary": "Hebelstellwerk aus Altenau im Harz",
            "description": "Gedruckt in Resin.\n\nMit Treppenhaus.",
            "primary_category_id": category["id"],
            "epoch_codes": ["III"],
        },
        headers={"If-Match": f'"{product["version"]}"'},
    )
    assert response.status_code == 200, response.text
    response = await staff_client.post(
        f"{PRODUCTS}/{product_id}/scales",
        json={"scale_code": "H0", "length_mm": 112.5, "width_mm": 64.0, "weight_g": 85},
    )
    assert response.status_code == 201, response.text
    scale_id = response.json()["scales"][0]["id"]
    for finish, price in (("unpainted", 3490), ("painted", 7990)):
        response = await staff_client.post(
            f"/api/v1/admin/product-scales/{scale_id}/variants",
            json={"finish_code": finish, "price_cents": price},
        )
        assert response.status_code == 201, response.text
    image = await ready_image(media, media_storage, deliver, photo(1100, 800))
    response = await staff_client.post(
        f"{PRODUCTS}/{product_id}/media", json={"asset_id": str(image.id), "alt_text": "Front"}
    )
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


class TestEditing:
    async def test_create_answers_with_etag_and_location(self, staff_client: AsyncClient) -> None:
        response = await create(staff_client)
        product = response.json()
        assert etag(response) == '"1"'
        assert response.headers["location"] == f"{PRODUCTS}/{product['id']}"
        assert product["slug"] == "stellwerk-altenau"
        assert product["status"] == "draft"
        assert product["publish_blockers"] == ["no_category", "no_active_variant", "no_main_image"]
        fetched = await staff_client.get(f"{PRODUCTS}/{product['id']}")
        assert etag(fetched) == '"1"'

    async def test_patch_needs_the_current_version(self, staff_client: AsyncClient) -> None:
        product = (await create(staff_client)).json()
        url = f"{PRODUCTS}/{product['id']}"
        assert_problem(
            await staff_client.patch(url, json={"summary": "x"}), 428, "precondition_required"
        )
        assert_problem(
            await staff_client.patch(url, json={"summary": "x"}, headers={"If-Match": '"7"'}),
            412,
            "precondition_failed",
        )
        assert_problem(
            await staff_client.patch(url, json={"summary": "x"}, headers={"If-Match": "abc"}),
            412,
            "precondition_failed",
        )
        response = await staff_client.patch(
            url, json={"summary": "Kurz und knapp"}, headers={"If-Match": 'W/"1"'}
        )
        assert response.status_code == 200, response.text
        assert etag(response) == '"2"'
        assert response.json()["summary"] == "Kurz und knapp"

    async def test_patch_changes_only_what_is_sent(self, staff_client: AsyncClient) -> None:
        category = (await staff_client.post(CATEGORIES, json={"name": "Gebäude"})).json()
        product = (await create(staff_client)).json()
        url = f"{PRODUCTS}/{product['id']}"
        first = await staff_client.patch(
            url,
            json={"primary_category_id": category["id"], "prototype": "Altenau"},
            headers={"If-Match": etag_of(product)},
        )
        second = await staff_client.patch(
            url, json={"primary_category_id": None}, headers={"If-Match": etag(first)}
        )
        assert second.json()["primary_category_id"] is None
        assert second.json()["prototype"] == "Altenau"
        body = assert_problem(
            await staff_client.patch(
                url, json={"epoch_codes": ["VIII"]}, headers={"If-Match": etag(second)}
            ),
            422,
            "validation_failed",
        )
        assert body["errors"][0]["field"] == "epoch_codes"
        assert body["errors"][0]["code"] == "unknown"

    async def test_colours_of_a_finished_model(self, staff_client: AsyncClient) -> None:
        product = (await create(staff_client)).json()
        scales = await staff_client.post(
            f"{PRODUCTS}/{product['id']}/scales", json={"scale_code": "H0"}
        )
        url = f"/api/v1/admin/product-scales/{scales.json()['scales'][0]['id']}/variants"
        await staff_client.post(
            url, json={"finish_code": "painted", "color": "gelb", "price_cents": 8000}
        )
        response = await staff_client.post(
            url, json={"finish_code": "painted", "color": "Blau", "price_cents": 8000}
        )
        variants = response.json()["scales"][0]["variants"]
        number = f"MB-{product['number']:06d}-H0"
        assert [(v["color"], v["sku"]) for v in variants] == [
            ("Gelb", f"{number}-F"),
            ("Blau", f"{number}-F2"),
        ]
        kit = await staff_client.post(
            url, json={"finish_code": "unpainted", "color": "Rot", "price_cents": 3000}
        )
        assert_problem(kit, 422, "validation_failed")
        assert kit.json()["errors"][0]["code"] == "not_colored"
        primed = await staff_client.post(url, json={"finish_code": "primed", "price_cents": 3000})
        assert primed.json()["errors"][0]["code"] == "not_offered"
        assert_problem(
            await staff_client.patch(
                f"/api/v1/admin/variants/{variants[1]['id']}", json={"color": "GELB"}
            ),
            409,
            "variant_exists",
        )

    async def test_variants(self, staff_client: AsyncClient) -> None:
        product = (await create(staff_client)).json()
        scales = await staff_client.post(
            f"{PRODUCTS}/{product['id']}/scales", json={"scale_code": "N"}
        )
        scale_id = scales.json()["scales"][0]["id"]
        url = f"/api/v1/admin/product-scales/{scale_id}/variants"
        response = await staff_client.post(
            url,
            json={"finish_code": "unpainted", "price_cents": 1990, "compare_at_price_cents": 2490},
        )
        (variant,) = response.json()["scales"][0]["variants"]
        assert variant["sku"] == f"MB-{product['number']:06d}-N-B"
        assert len(variant["gtin"]) == 13
        assert_problem(
            await staff_client.post(url, json={"finish_code": "unpainted", "price_cents": 1}),
            409,
            "variant_exists",
        )
        variant_url = f"/api/v1/admin/variants/{variant['id']}"
        changed = await staff_client.patch(
            variant_url, json={"price_cents": 1790, "compare_at_price_cents": None}
        )
        (variant,) = changed.json()["scales"][0]["variants"]
        assert (variant["price_cents"], variant["compare_at_price_cents"]) == (1790, None)
        body = assert_problem(
            await staff_client.patch(variant_url, json={"compare_at_price_cents": 100}),
            422,
            "validation_failed",
        )
        assert body["errors"][0]["code"] == "not_above_price"
        dims = await staff_client.patch(
            f"/api/v1/admin/product-scales/{scale_id}", json={"height_mm": 33.33}
        )
        assert dims.json()["scales"][0]["height_mm"] == 33.3
        removed = await staff_client.delete(variant_url)
        assert removed.json()["scales"][0]["variants"] == []
        assert_problem(await staff_client.delete(variant_url), 404, "variant_not_found")
        gone = await staff_client.delete(f"/api/v1/admin/product-scales/{scale_id}")
        assert gone.json()["scales"] == []

    async def test_gallery_needs_if_match_to_be_arranged(
        self,
        staff_client: AsyncClient,
        media: MediaService,
        media_storage: InMemoryMediaStorage,
        deliver: Deliver,
    ) -> None:
        product = await publishable(staff_client, media, media_storage, deliver)
        url = f"{PRODUCTS}/{product['id']}/media"
        (entry,) = product["media"]
        assert entry["image"]["status"] == "ready"
        assert entry["image"]["renditions"]
        entries = {"entries": [{"asset_id": entry["asset_id"], "alt_text": "Neu"}]}
        assert_problem(await staff_client.put(url, json=entries), 428, "precondition_required")
        response = await staff_client.put(url, json=entries, headers={"If-Match": etag_of(product)})
        assert response.status_code == 200, response.text
        assert response.json()["media"][0]["alt_text"] == "Neu"


def etag_of(product: dict[str, Any]) -> str:
    return f'"{product["version"]}"'


class TestPublishing:
    async def test_not_publishable_lists_what_is_missing(self, staff_client: AsyncClient) -> None:
        product = (await create(staff_client)).json()
        body = assert_problem(
            await staff_client.post(f"{PRODUCTS}/{product['id']}/publish"), 422, "not_publishable"
        )
        assert [e["code"] for e in body["errors"]] == [
            "no_category",
            "no_active_variant",
            "no_main_image",
        ]

    async def test_publish_archive_and_the_shop(
        self,
        staff_client: AsyncClient,
        client: AsyncClient,
        media: MediaService,
        media_storage: InMemoryMediaStorage,
        deliver: Deliver,
    ) -> None:
        product = await publishable(staff_client, media, media_storage, deliver)
        assert product["publish_blockers"] == []
        assert (await client.get(f"{SHOP}/products/{product['slug']}")).status_code == 404

        published = await staff_client.post(
            f"{PRODUCTS}/{product['id']}/publish", headers={"If-Match": etag_of(product)}
        )
        assert published.status_code == 200, published.text
        assert published.json()["status"] == "active"
        assert_problem(
            await staff_client.post(f"{PRODUCTS}/{product['id']}/publish"),
            409,
            "invalid_product_state",
        )

        listing = await client.get(f"{SHOP}/products")
        assert listing.headers["cache-control"] == "public, max-age=60"
        (card,) = listing.json()["items"]
        assert card["slug"] == "stellwerk-altenau"
        assert card["scale_codes"] == ["H0"]
        assert card["price_from_cents"] == 3490
        assert card["image"]["lqip"].startswith("data:image/webp")

        page = (await client.get(f"{SHOP}/products/stellwerk-altenau")).json()
        assert page["category_path"] == [{"slug": "stellwerke", "name": "Stellwerke"}]
        assert page["epochs"] == [{"code": "III", "name": "Epoche III", "period": "1949–1970"}]  # noqa: RUF001
        (scale,) = page["scales"]
        assert (scale["code"], scale["ratio"], scale["track_gauge_mm"]) == ("H0", "1:87", 16.5)
        navigation = (await client.get(f"{SHOP}/navigation")).json()
        h0 = next(s for s in navigation["scales"] if s["code"] == "H0")
        assert (h0["ratio_denominator"], h0["product_count"]) == (87, 1)
        (category,) = navigation["categories"]
        assert category["product_counts"] == {"H0": 1}
        assert (scale["length_mm"], scale["weight_g"]) == (112.5, 85)
        assert [v["finish_code"] for v in scale["variants"]] == ["unpainted", "painted"]
        assert "gtin" not in scale["variants"][0]
        (item,) = page["gallery"]
        assert item["alt_text"] == "Front"
        assert {r["format"] for r in item["image"]["renditions"]} == {"webp", "avif"}
        assert [f["name"] for f in page["finishes"]] == ["Bausatz", "Fertigmodell"]

        assert_problem(
            await staff_client.patch(
                f"{PRODUCTS}/{product['id']}",
                json={"slug": "anders"},
                headers={"If-Match": etag(published)},
            ),
            409,
            "slug_locked",
        )
        archived = await staff_client.post(f"{PRODUCTS}/{product['id']}/archive")
        assert archived.json()["status"] == "archived"
        assert (await client.get(f"{SHOP}/products")).json()["items"] == []
        assert_problem(
            await staff_client.delete(f"{PRODUCTS}/{product['id']}"), 409, "product_not_deletable"
        )


class TestCategoriesAndLists:
    async def test_categories(self, staff_client: AsyncClient, client: AsyncClient) -> None:
        top = (await staff_client.post(CATEGORIES, json={"name": "Gebäude"})).json()
        child = await staff_client.post(
            CATEGORIES, json={"name": "Stellwerke", "parent_id": top["id"]}
        )
        assert child.status_code == 201
        assert_problem(
            await staff_client.post(CATEGORIES, json={"name": "Gebäude"}), 409, "slug_taken"
        )
        body = assert_problem(
            await staff_client.patch(
                f"{CATEGORIES}/{top['id']}", json={"parent_id": child.json()["id"]}
            ),
            422,
            "validation_failed",
        )
        assert body["errors"][0] == {
            "field": "parent_id",
            "code": "cycle",
            "message": body["errors"][0]["message"],
        }
        listed = (await staff_client.get(CATEGORIES)).json()
        assert [c["slug"] for c in listed] == ["gebaeude", "stellwerke"]
        navigation = (await client.get(f"{SHOP}/navigation")).json()
        assert [c["slug"] for c in navigation["categories"]] == ["gebaeude", "stellwerke"]
        assert [s["code"] for s in navigation["scales"]] == [
            "Z",
            "N",
            "TT",
            "H0",
            "0",
            "125",
            "124",
            "G",
        ]
        assert navigation["categories"][0]["product_counts"] == {}
        assert len(navigation["epochs"]) == 6

    async def test_admin_list_with_cursor(self, staff_client: AsyncClient) -> None:
        for name in ("Erstes", "Zweites", "Drittes"):
            await create(staff_client, name)
        first = (await staff_client.get(PRODUCTS, params={"limit": 2})).json()
        assert [p["name"] for p in first["items"]] == ["Drittes", "Zweites"]
        second = (
            await staff_client.get(PRODUCTS, params={"limit": 2, "cursor": first["next_cursor"]})
        ).json()
        assert [p["name"] for p in second["items"]] == ["Erstes"]
        assert second["next_cursor"] is None
        drafts = (await staff_client.get(PRODUCTS, params={"status": "active"})).json()
        assert drafts["items"] == []
        references = (await staff_client.get("/api/v1/admin/catalog/references")).json()
        assert [(f["sku_letter"], f["offered"]) for f in references["finishes"]] == [
            ("B", True),
            ("F", True),
            ("G", False),
        ]

    @pytest.mark.parametrize(
        ("path", "status", "code"),
        [
            (f"{SHOP}/products/gibt-es-nicht", 404, "product_not_found"),
            (f"{SHOP}/products?category=gibt-es-nicht", 404, "category_not_found"),
            (f"{SHOP}/products?scale=QQ", 422, "validation_failed"),
            (f"{SHOP}/products?cursor=kaputt", 422, "validation_failed"),
        ],
    )
    async def test_shop_errors(
        self, client: AsyncClient, path: str, status: int, code: str
    ) -> None:
        assert_problem(await client.get(path), status, code)

    async def test_only_back_office_staff(
        self, client: AsyncClient, packer_client: AsyncClient
    ) -> None:
        assert_problem(await client.get(PRODUCTS), 401, "not_authenticated")
        assert_problem(await packer_client.get(PRODUCTS), 403, "insufficient_role")
        assert_problem(
            await packer_client.post(f"{PRODUCTS}/{uuid4()}/publish"), 403, "insufficient_role"
        )


SCALES = "/api/v1/admin/scales"


class TestScales:
    async def test_add_correct_and_remove_a_scale(self, staff_client: AsyncClient) -> None:
        created = await staff_client.post(
            SCALES, json={"code": "43", "name": "1:43,5", "ratio_denominator": 43.5}
        )
        assert created.status_code == 201, created.text
        assert created.json() == {
            "code": "43",
            "name": "1:43,5",
            "ratio": "1:43,5",
            "ratio_denominator": 43.5,
            "track_gauge_mm": None,
            "product_count": 0,
        }
        listed = (await staff_client.get(SCALES)).json()
        assert [s["code"] for s in listed] == ["Z", "N", "TT", "H0", "0", "43", "125", "124", "G"]

        changed = await staff_client.patch(f"{SCALES}/0", json={"track_gauge_mm": None})
        assert changed.json()["track_gauge_mm"] is None
        renamed = await staff_client.patch(f"{SCALES}/0", json={"name": "Null"})
        assert (renamed.json()["name"], renamed.json()["track_gauge_mm"]) == ("Null", None)

        assert (await staff_client.delete(f"{SCALES}/43")).status_code == 204
        assert_problem(await staff_client.delete(f"{SCALES}/43"), 404, "scale_not_found")

    async def test_refuses_duplicates_and_odd_numbers(self, staff_client: AsyncClient) -> None:
        body = assert_problem(
            await staff_client.post(
                SCALES, json={"code": "h0", "name": "Neu", "ratio_denominator": 87}
            ),
            422,
            "validation_failed",
        )
        assert [(e["field"], e["code"]) for e in body["errors"]] == [("code", "duplicate")]
        body = assert_problem(
            await staff_client.post(
                SCALES, json={"code": "S", "name": "S", "ratio_denominator": 64.25}
            ),
            422,
            "validation_failed",
        )
        assert [(e["field"], e["code"]) for e in body["errors"]] == [
            ("ratio_denominator", "invalid")
        ]

    async def test_a_scale_in_use_stays(self, staff_client: AsyncClient) -> None:
        product = (await create(staff_client)).json()
        added = await staff_client.post(
            f"{PRODUCTS}/{product['id']}/scales", json={"scale_code": "124"}
        )
        assert added.status_code == 201, added.text
        assert_problem(await staff_client.delete(f"{SCALES}/124"), 409, "scale_in_use")
        listed = {s["code"]: s for s in (await staff_client.get(SCALES)).json()}
        assert listed["124"]["product_count"] == 1

    async def test_only_back_office_staff(
        self, client: AsyncClient, packer_client: AsyncClient
    ) -> None:
        assert_problem(await client.get(SCALES), 401, "not_authenticated")
        assert_problem(await packer_client.get(SCALES), 403, "insufficient_role")
        assert_problem(await packer_client.delete(f"{SCALES}/Z"), 403, "insufficient_role")
