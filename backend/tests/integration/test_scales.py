"""Maintaining scales: adding 1:24, correcting, removing only what nothing uses."""

from decimal import Decimal

import pytest

from modellbahn.modules.catalog.application.scales import ScaleService
from modellbahn.modules.catalog.application.services import CatalogService
from modellbahn.modules.catalog.domain.errors import (
    InvalidFieldError,
    ScaleInUseError,
    ScaleNotFoundError,
)
from modellbahn.modules.catalog.domain.model import Dimensions
from modellbahn.modules.catalog.infrastructure.repositories import SqlReferenceData


async def test_lists_the_smallest_models_first_with_their_use(
    scale_service: ScaleService, catalog: CatalogService
) -> None:
    product = await catalog.create_product(name="Stellwerk Altenau")
    await catalog.add_scale(
        product.product.id, expected_version=None, scale_code="N", dimensions=Dimensions()
    )

    scales = await scale_service.list_scales()

    assert [(u.scale.code, u.scale.ratio, u.product_count) for u in scales] == [
        ("Z", "1:220", 0),
        ("N", "1:160", 1),
        ("TT", "1:120", 0),
        ("H0", "1:87", 0),
        ("0", "1:45", 0),
        ("125", "1:25", 0),
        ("124", "1:24", 0),
        ("G", "1:22,5", 0),
    ]


async def test_a_new_scale_takes_products_and_sku(
    scale_service: ScaleService, catalog: CatalogService
) -> None:
    created = await scale_service.create_scale(
        code=" s ", name="S", ratio_denominator=Decimal("64"), track_gauge_mm=Decimal("22.5")
    )
    assert (created.scale.code, created.scale.ratio, created.product_count) == ("S", "1:64", 0)

    details = await catalog.create_product(name="Feldbahnlok")
    details = await catalog.add_scale(
        details.product.id, expected_version=None, scale_code="S", dimensions=Dimensions()
    )
    details = await catalog.add_variant(
        details.product.scales[0].id, expected_version=None, finish_code="primed", price_cents=990
    )
    assert details.product.scales[0].variants[0].sku.endswith("-S-G")


async def test_road_scales_need_no_track_and_ratios_may_have_a_decimal(
    scale_service: ScaleService,
) -> None:
    created = await scale_service.create_scale(
        code="43", name="1:43,5", ratio_denominator=Decimal("43.5"), track_gauge_mm=None
    )
    assert (created.scale.ratio, created.scale.track_gauge_mm) == ("1:43,5", None)


@pytest.mark.parametrize(
    ("changes", "field", "code"),
    [
        ({"code": "1:24"}, "code", "invalid"),
        ({"code": "124"}, "code", "duplicate"),
        ({"name": "H0"}, "name", "duplicate"),
        ({"ratio_denominator": Decimal("22.25")}, "ratio_denominator", "invalid"),
        ({"ratio_denominator": Decimal(1)}, "ratio_denominator", "out_of_range"),
        ({"track_gauge_mm": Decimal(0)}, "track_gauge_mm", "out_of_range"),
    ],
)
async def test_refuses_what_breaks_a_rule(
    scale_service: ScaleService, changes: dict[str, object], field: str, code: str
) -> None:
    values: dict[str, object] = {
        "code": "S",
        "name": "S",
        "ratio_denominator": Decimal(64),
        "track_gauge_mm": None,
    } | changes
    with pytest.raises(InvalidFieldError) as caught:
        await scale_service.create_scale(**values)  # type: ignore[arg-type]
    assert (caught.value.field, caught.value.code) == (field, code)


async def test_changes_name_ratio_and_gauge_but_not_the_code(scale_service: ScaleService) -> None:
    changed = await scale_service.change_scale(
        "0", name="0 (1:43,5)", ratio_denominator=Decimal("43.5"), track_gauge_mm=None
    )
    assert (changed.scale.code, changed.scale.name, changed.scale.ratio) == (
        "0",
        "0 (1:43,5)",
        "1:43,5",
    )
    assert changed.scale.track_gauge_mm is None
    listed = {u.scale.code: u.scale for u in await scale_service.list_scales()}
    assert listed["0"].ratio_denominator == Decimal("43.5")

    with pytest.raises(InvalidFieldError) as caught:
        await scale_service.change_scale("0", name="G")
    assert (caught.value.field, caught.value.code) == ("name", "duplicate")
    with pytest.raises(ScaleNotFoundError):
        await scale_service.change_scale("QQ", name="Q")


async def test_removes_only_unused_scales(
    scale_service: ScaleService, catalog: CatalogService
) -> None:
    product = await catalog.create_product(name="Kipper")
    await catalog.add_scale(
        product.product.id, expected_version=None, scale_code="125", dimensions=Dimensions()
    )

    with pytest.raises(ScaleInUseError):
        await scale_service.delete_scale("125")
    await scale_service.delete_scale("124")
    with pytest.raises(ScaleNotFoundError):
        await scale_service.delete_scale("124")

    assert "124" not in {u.scale.code for u in await scale_service.list_scales()}


async def _never(*_: object, **__: object) -> bool:
    return False


async def test_the_database_settles_a_race_the_checks_missed(
    scale_service: ScaleService, catalog: CatalogService, monkeypatch: pytest.MonkeyPatch
) -> None:
    # As if a colleague had saved between the check and the commit.
    monkeypatch.setattr(SqlReferenceData, "scale_taken", _never)
    monkeypatch.setattr(SqlReferenceData, "scale_in_use", _never)
    product = await catalog.create_product(name="Kipper")
    await catalog.add_scale(
        product.product.id, expected_version=None, scale_code="125", dimensions=Dimensions()
    )

    for duplicate, field in ((("H0", "Neu"), "code"), (("S", "H0"), "name")):
        with pytest.raises(InvalidFieldError) as caught:
            await scale_service.create_scale(
                code=duplicate[0],
                name=duplicate[1],
                ratio_denominator=Decimal(64),
                track_gauge_mm=None,
            )
        assert (caught.value.field, caught.value.code) == (field, "duplicate")
    with pytest.raises(ScaleInUseError):
        await scale_service.delete_scale("125")
