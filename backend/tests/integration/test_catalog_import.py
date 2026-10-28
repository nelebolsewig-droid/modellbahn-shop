"""The starting catalogue: the seed file, and importing it into the catalogue."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from modellbahn.modules.catalog.api.seed_file import SeedFile
from modellbahn.modules.catalog.application.importing import (
    CatalogSeed,
    CategorySeed,
    ProductSeed,
    ScaleSeed,
    SeedError,
    import_catalog,
)
from modellbahn.modules.catalog.application.services import CatalogService
from modellbahn.modules.catalog.domain.model import ProductStatus
from tests.support import BACKEND_ROOT

START = BACKEND_ROOT / "seed" / "startbestand.json"


def test_the_start_file_reads() -> None:
    seed = SeedFile.read(START).to_seed()
    names = [p.name for p in seed.products]
    assert len(names) == len(set(names))
    assert "ADK III3 Puma Kran-2" in names
    # Offered finishes only, and colours only on the finished model.
    for product in seed.products:
        for scale in product.scales:
            for variant in scale.variants:
                assert variant.finish_code in {"unpainted", "painted"}
                assert variant.finish_code == "painted" or variant.color == ""


@pytest.mark.parametrize(
    ("change", "where"),
    [
        ({"finish": "primed"}, "finish"),
        ({"preis": 10}, "preis"),
        ({"price_cents": -1}, "price_cents"),
    ],
)
def test_a_wrong_file_stops_before_anything_is_written(
    tmp_path: Path, change: dict[str, object], where: str
) -> None:
    variant = {"finish": "painted", "price_cents": 1000} | change
    target = tmp_path / "seed.json"
    target.write_text(
        '{"categories": [{"name": "Kranfahrzeuge"}], "products": [{"name": "Kran", '
        '"category": "Kranfahrzeuge", "scales": [{"code": "H0", "variants": ['
        + json.dumps(variant)
        + "]}]}]}",
        encoding="utf-8",
    )
    with pytest.raises(ValidationError, match=where):
        SeedFile.read(target)


async def test_imports_the_start_file_once(catalog: CatalogService) -> None:
    seed = SeedFile.read(START).to_seed()
    first = await import_catalog(catalog, seed)
    assert len(first.products) == len(seed.products)
    assert "Straßenfahrzeuge / LKW / Kipper" in first.categories
    assert ("IFA ADK 125 Autokran", "laut Shopify ausverkauft") in first.notes

    puma = await catalog.find_product("adk-iii3-puma-kran-2")
    assert puma is not None
    assert puma.status is ProductStatus.DRAFT
    (h0,) = puma.scales
    assert [(v.color, v.sku.rsplit("-", 1)[1], v.price_cents) for v in h0.variants] == [
        ("Blau", "F", 6500),
        ("Grün", "F2", 6500),
        ("Grau", "F3", 6500),
        ("Hellblau", "F4", 6500),
    ]
    tipper = await catalog.find_product("tatra-148-kipper")
    assert tipper is not None
    assert [s.variants for s in tipper.scales] == [[]]
    categories = {c.id: c for c in await catalog.list_categories()}
    assert tipper.primary_category_id is not None
    assert categories[tipper.primary_category_id].name == "Kipper"

    again = await import_catalog(catalog, seed)
    assert (again.categories, again.products) == ([], [])
    assert again.skipped == [p.name for p in seed.products]
    assert len(await catalog.list_categories()) == len(categories)


async def test_joins_the_tree_that_exists_and_finds_free_addresses(catalog: CatalogService) -> None:
    roads = await catalog.create_category(name="Straßenfahrzeuge")
    trucks = await catalog.create_category(name="Lkw", parent_id=roads.id)
    # Another "Kipper" elsewhere already has the address "kipper".
    trailers = await catalog.create_category(name="Anhänger")
    await catalog.create_category(name="Kipper", parent_id=trailers.id)
    seed = CatalogSeed(
        categories=[
            CategorySeed(
                name="Straßenfahrzeuge", children=[CategorySeed("LKW", [CategorySeed("Kipper")])]
            ),
        ],
        products=[ProductSeed(name="Tatra 148 Kipper", category="Straßenfahrzeuge / LKW / Kipper")],
    )

    report = await import_catalog(catalog, seed)

    assert report.categories == ["Straßenfahrzeuge / LKW / Kipper"]
    by_id = {c.id: c for c in await catalog.list_categories()}
    tipper = await catalog.find_product("tatra-148-kipper")
    assert tipper is not None
    assert tipper.primary_category_id is not None
    category = by_id[tipper.primary_category_id]
    assert (category.parent_id, category.slug) == (trucks.id, "lkw-kipper")


async def test_an_unknown_category_or_scale_writes_nothing(catalog: CatalogService) -> None:
    seed = CatalogSeed(
        categories=[CategorySeed(name="Kranfahrzeuge")],
        products=[
            ProductSeed(name="Kran", category="Kranfahrzeuge", scales=[ScaleSeed("Q7")]),
            ProductSeed(name="Kipper", category="LKW / Kipper"),
        ],
    )
    with pytest.raises(SeedError) as raised:
        await import_catalog(catalog, seed)
    assert "Kran: unknown scale 'Q7'" in str(raised.value)
    assert "Kipper: unknown category 'LKW / Kipper'" in str(raised.value)
    assert await catalog.list_categories() == []
    assert await catalog.find_product("kran") is None
