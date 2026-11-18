"""The store's worth: finished pieces on the shelves at today's price, parts by number."""

from dataclasses import replace
from uuid import uuid4

from modellbahn.modules.catalog.contracts.variants import SaleVariant
from modellbahn.modules.inventory.application.ports import StockCount
from modellbahn.modules.inventory.application.valuation import stock_value
from modellbahn.modules.inventory.domain.model import UnitStatus

KRAN = SaleVariant(
    variant_id=uuid4(),
    gtin="2000000000428",
    product_id=uuid4(),
    product_scale_id=uuid4(),
    product_slug="edk-6",
    product_name="EDK 6",
    scale_code="H0",
    scale_name="H0",
    finish_code="painted",
    finish_name="Fertigmodell",
    color="",
    sku="MB-000042-H0-B",
    price_cents=8990,
    compare_at_price_cents=12000,
    image_asset_id=None,
    purchasable=True,
    allow_backorder=False,
    lead_time_weeks=None,
)
KRAN_KIT = replace(
    KRAN, variant_id=uuid4(), finish_code="unpainted", finish_name="Bausatz", price_cents=3990
)
KRAN_TT = replace(KRAN, variant_id=uuid4(), scale_code="TT", scale_name="TT", price_cents=7490)
LOK = replace(KRAN, variant_id=uuid4(), product_id=uuid4(), product_name="BR 01", price_cents=20000)
VARIANTS = {v.variant_id: v for v in (KRAN, KRAN_KIT, KRAN_TT, LOK)}


def count(variant: SaleVariant, status: UnitStatus, number: int) -> StockCount:
    return StockCount(variant_id=variant.variant_id, status=status, count=number)


def test_only_pieces_on_the_shelves_count_at_todays_price() -> None:
    value = stock_value(
        [
            count(KRAN, UnitStatus.IN_STOCK, 3),
            count(KRAN, UnitStatus.ALLOCATED, 1),
            # Not in the store: never put away, being packed, gone.
            count(KRAN, UnitStatus.LABELED, 5),
            count(KRAN, UnitStatus.PICKED, 2),
            count(KRAN, UnitStatus.SHIPPED, 9),
            count(KRAN, UnitStatus.SCRAPPED, 1),
        ],
        VARIANTS,
        {},
    )
    # The price now, not the "was" price.
    assert (value.pieces, value.value_cents) == (4, 4 * 8990)
    assert (value.free_pieces, value.free_cents) == (3, 3 * 8990)
    assert (value.reserved_pieces, value.reserved_cents) == (1, 8990)


def test_split_by_finish_scale_and_model_most_valuable_first() -> None:
    value = stock_value(
        [
            count(KRAN, UnitStatus.IN_STOCK, 2),
            count(KRAN_KIT, UnitStatus.IN_STOCK, 4),
            count(KRAN_TT, UnitStatus.ALLOCATED, 1),
            count(LOK, UnitStatus.IN_STOCK, 1),
        ],
        VARIANTS,
        {},
    )
    assert value.value_cents == 2 * 8990 + 4 * 3990 + 7490 + 20000
    assert [(s.name, s.pieces, s.value_cents) for s in value.by_finish] == [
        ("Fertigmodell", 4, 2 * 8990 + 7490 + 20000),
        ("Bausatz", 4, 4 * 3990),
    ]
    assert [(s.key, s.pieces) for s in value.by_scale] == [("H0", 7), ("TT", 1)]
    assert [(s.name, s.value_cents) for s in value.by_model] == [
        ("EDK 6", 2 * 8990 + 4 * 3990 + 7490),
        ("BR 01", 20000),
    ]
    assert value.by_model[0].key == str(KRAN.product_id)


def test_deleted_variants_and_parts_are_counted_not_priced() -> None:
    gone = uuid4()
    value = stock_value(
        [StockCount(variant_id=gone, status=UnitStatus.IN_STOCK, count=3)],
        VARIANTS,
        {uuid4(): 40, uuid4(): 12, uuid4(): 0},
    )
    assert (value.pieces, value.value_cents, value.unpriced_pieces) == (0, 0, 3)
    assert (value.part_pieces, value.part_kinds) == (52, 2)
    assert value.by_model == []


def test_an_empty_store_is_worth_nothing() -> None:
    value = stock_value([], VARIANTS, {})
    assert (value.pieces, value.value_cents, value.part_pieces) == (0, 0, 0)
