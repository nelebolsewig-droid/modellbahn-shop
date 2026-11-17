"""The hand-written migration: round trip, and agreement with the SQLAlchemy tables."""

import asyncio
import secrets
from collections.abc import Iterator
from typing import Any

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import Connection, text
from sqlalchemy.ext.asyncio import AsyncEngine

from modellbahn.modules.catalog.infrastructure import tables as catalog_tables
from modellbahn.modules.identity.infrastructure import tables as identity_tables
from modellbahn.modules.inventory.infrastructure import tables as inventory_tables
from modellbahn.modules.manufacturing.infrastructure import tables as manufacturing_tables
from modellbahn.modules.marketplace.infrastructure import tables as marketplace_tables
from modellbahn.modules.media.infrastructure import tables as media_tables
from modellbahn.modules.sales.infrastructure import tables as sales_tables
from modellbahn.platform import outbox
from modellbahn.platform.db import create_engine, metadata
from tests.support import create_database, downgrade, drop_database, migrate

SCHEMAS = (
    "platform",
    "identity",
    "media",
    "catalog",
    "sales",
    "inventory",
    "site",
    "marketplace",
    "manufacturing",
)


@pytest.fixture
def scratch_database_url(postgres_server_url: str) -> Iterator[str]:
    name = f"modellbahn_migration_{secrets.token_hex(6)}"
    url = asyncio.run(create_database(postgres_server_url, name))
    try:
        yield url
    finally:
        asyncio.run(drop_database(postgres_server_url, name))


async def _tables(database_url: str) -> set[str]:
    engine = create_engine(database_url)
    try:
        async with engine.connect() as connection:
            rows = await connection.execute(
                text(
                    "SELECT table_schema || '.' || table_name FROM information_schema.tables "
                    "WHERE table_schema = ANY(:schemas)"
                ),
                {"schemas": list(SCHEMAS)},
            )
            return set(rows.scalars())
    finally:
        await engine.dispose()


def test_upgrade_downgrade_upgrade(scratch_database_url: str) -> None:
    expected = {
        "platform.outbox",
        "identity.accounts",
        "identity.sessions",
        "identity.account_tokens",
        "media.assets",
        "media.image_details",
        "media.renditions",
        "catalog.scales",
        "catalog.finishes",
        "catalog.epochs",
        "catalog.categories",
        "catalog.products",
        "catalog.product_epochs",
        "catalog.product_scales",
        "catalog.variants",
        "catalog.product_media",
        "catalog.production_settings",
        "sales.carts",
        "sales.cart_lines",
        "sales.orders",
        "sales.order_lines",
        "sales.payments",
        "sales.customer_addresses",
        "sales.withdrawals",
        "sales.shipping_labels",
        "inventory.locations",
        "inventory.allocations",
        "inventory.units",
        "inventory.scans",
        "inventory.stock_ledger",
        "inventory.part_stock",
        "inventory.part_receipts",
        "inventory.part_ledger",
        "site.fairs",
        "site.subscriptions",
        "site.mailings",
        "marketplace.ebay_account",
        "marketplace.category_map",
        "marketplace.listings",
        "marketplace.listing_items",
        "marketplace.marketplace_orders",
        "marketplace.marketplace_order_lines",
        "marketplace.test_sales",
        "manufacturing.printers",
        "manufacturing.printer_status_reports",
        "manufacturing.materials",
        "manufacturing.parts",
        "manufacturing.boms",
        "manufacturing.bom_lines",
        "manufacturing.print_jobs",
        "manufacturing.print_job_lines",
    }
    migrate(scratch_database_url)
    assert asyncio.run(_tables(scratch_database_url)) == expected
    downgrade(scratch_database_url)
    assert asyncio.run(_tables(scratch_database_url)) == set()
    migrate(scratch_database_url)
    assert asyncio.run(_tables(scratch_database_url)) == expected


def _include(name: str | None, type_: str, parent_names: Any) -> bool:
    if type_ == "schema":
        return name in SCHEMAS
    return True


def _differences(connection: Connection) -> list[Any]:
    context = MigrationContext.configure(
        connection, opts={"include_schemas": True, "include_name": _include}
    )
    return list(compare_metadata(context, metadata))


async def test_tables_match_the_migration(engine: AsyncEngine) -> None:
    # Every module's tables are registered on the shared metadata.
    assert outbox.outbox_table.metadata is metadata
    assert identity_tables.accounts.metadata is metadata
    assert media_tables.assets.metadata is metadata
    assert catalog_tables.products.metadata is metadata
    assert sales_tables.orders.metadata is metadata
    assert inventory_tables.units.metadata is metadata
    assert marketplace_tables.listings.metadata is metadata
    assert manufacturing_tables.print_jobs.metadata is metadata
    async with engine.connect() as connection:
        assert await connection.run_sync(_differences) == []


async def test_constraint_names_follow_the_convention(engine: AsyncEngine) -> None:
    async with engine.connect() as connection:
        rows = await connection.execute(
            text(
                "SELECT conname FROM pg_constraint c JOIN pg_namespace n ON n.oid = c.connamespace "
                "WHERE n.nspname = ANY(:schemas)"
            ),
            {"schemas": list(SCHEMAS)},
        )
        names = set(rows.scalars())
    assert {
        "pk_outbox",
        "ck_outbox_published_at",
        "uq_accounts_kind_email",
        "uq_accounts_id_kind",
        "ck_accounts_role_only_for_staff",
        "fk_sessions_account_id_kind_accounts",
        "uq_account_tokens_source_event_id",
        "fk_account_tokens_account_id_accounts",
        "uq_assets_id_kind",
        "fk_image_details_asset_id_asset_kind_assets",
        "uq_product_media_product_id_position",
        "fk_product_media_asset_id_asset_kind_assets",
        "uq_variants_product_scale_id_finish_code_color",
        "ck_variants_kit_without_color",
        "ck_variants_gtin_format",
        "uq_orders_checkout_key",
        "uq_payments_idempotency_key",
        "ck_orders_total_is_sum",
        "fk_orders_customer_account_id_customer_kind_accounts",
        "fk_customer_addresses_account_id_account_kind_accounts",
        "ex_customer_addresses_one_default",
        "ck_scales_code_format",
        "ck_scales_ratio_range",
        "uq_scales_name",
        "ck_locations_site_is_root",
        "ck_units_on_shelf",
        "ck_units_serves_allocation",
        "uq_units_allocation_id",
        "fk_units_variant_id_variants",
        "fk_allocations_order_id_orders",
        "fk_stock_ledger_reverses_id_stock_ledger",
        "ck_stock_ledger_undo_reverses",
        "uq_product_scales_id_scale_code",
        "fk_boms_product_scale_id_scale_code_product_scales",
        "fk_bom_lines_part_id_scale_code_parts",
        "fk_parts_material_id_technology_materials",
        "fk_print_jobs_printer_id_technology_printers",
        "fk_print_job_lines_part_id_technology_parts",
        "ck_print_job_lines_counts_within_quantity",
        "ck_print_jobs_started_at",
    } <= names


@pytest.mark.usefixtures("clean_database")
async def test_scales_start_with_rail_and_road_scales(engine: AsyncEngine) -> None:
    async with engine.connect() as connection:
        rows = await connection.execute(
            text(
                "SELECT code, name, ratio_denominator, track_gauge_mm FROM catalog.scales "
                "ORDER BY ratio_denominator DESC"
            )
        )
        scales = [
            (code, name, str(ratio), gauge and str(gauge)) for code, name, ratio, gauge in rows
        ]
    assert scales == [
        ("Z", "Z", "220.0", "6.5"),
        ("N", "N", "160.0", "9.0"),
        ("TT", "TT", "120.0", "12.0"),
        ("H0", "H0", "87.0", "16.5"),
        ("0", "0", "45.0", "32.0"),
        ("125", "1:25", "25.0", None),
        ("124", "1:24", "24.0", None),
        ("G", "G", "22.5", "45.0"),
    ]


_VARIANTS_BEFORE_0020 = """
INSERT INTO catalog.products (id, number, slug, name, status, created_at, updated_at)
VALUES ('00000000-0000-7000-8000-000000000001', 1, 'kipper', 'Kipper', 'draft', now(), now());
INSERT INTO catalog.product_scales (id, product_id, scale_code)
VALUES ('00000000-0000-7000-8000-000000000002', '00000000-0000-7000-8000-000000000001', 'H0');
INSERT INTO catalog.variants (id, product_scale_id, finish_code, color, sku, gtin,
    price_cents, allow_backorder, lead_time_min_weeks, lead_time_max_weeks,
    created_at, updated_at)
VALUES
    ('00000000-0000-7000-8000-00000000000a', '00000000-0000-7000-8000-000000000002',
     'unpainted', '', 'MB-000001-H0-B', '2000000000011', 2990, true, 6, 8, now(), now()),
    ('00000000-0000-7000-8000-00000000000b', '00000000-0000-7000-8000-000000000002',
     'painted', 'Rot', 'MB-000001-H0-FRO', '2000000000028', 4990, false, 3, 3, now(), now()),
    ('00000000-0000-7000-8000-00000000000c', '00000000-0000-7000-8000-000000000002',
     'painted', 'Gelb', 'MB-000001-H0-FGE', '2000000000035', 4990, false, NULL, NULL,
     now(), now());
"""


async def _variant_rows(database_url: str) -> list[tuple[str, bool, int | None, int | None]]:
    engine = create_engine(database_url)
    try:
        async with engine.connect() as connection:
            rows = await connection.execute(
                text(
                    "SELECT color, allow_backorder, lead_time_min_weeks, lead_time_max_weeks "
                    "FROM catalog.variants ORDER BY sku"
                )
            )
            return [(row[0], row[1], row[2], row[3]) for row in rows]
    finally:
        await engine.dispose()


async def _run(database_url: str, sql: str) -> None:
    engine = create_engine(database_url)
    try:
        async with engine.begin() as connection:
            for statement in filter(str.strip, sql.split(";")):
                await connection.execute(text(statement))
    finally:
        await engine.dispose()


def test_0020_makes_every_model_again(scratch_database_url: str) -> None:
    migrate(scratch_database_url, "0019")
    asyncio.run(_run(scratch_database_url, _VARIANTS_BEFORE_0020))

    migrate(scratch_database_url)
    # Made again, all of them. The lead time a made-to-order variant had stays its own;
    # one that was never used (not made to order) goes, so it follows the shop's.
    assert asyncio.run(_variant_rows(scratch_database_url)) == [
        ("", True, 6, 8),
        ("Gelb", True, None, None),
        ("Rot", True, None, None),
    ]

    downgrade(scratch_database_url, "0019")
    # Back again, the shop's lead time is copied where a variant had none of its own.
    assert asyncio.run(_variant_rows(scratch_database_url)) == [
        ("", True, 6, 8),
        ("Gelb", True, 2, 4),
        ("Rot", True, 2, 4),
    ]
