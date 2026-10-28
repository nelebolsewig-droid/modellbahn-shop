"""Inventory: locations, units, allocations, scans and the stock journal.

Written by hand like the migrations before; constraint names follow the naming
convention of ``modellbahn.platform.db``.

* Variants made to order get a lead time, a range of weeks the shop shows; those made
  to order already get 4 to 6 weeks.
* The outbox learns which handlers already succeeded for an event (``handled_by``): a
  paid order is now handled by sales (the confirmation mail) and by inventory
  (allocation), and a retry must run only the one that failed.

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-25
"""

from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_EMPTY = sa.text("''")


class _Ltree(sa.types.UserDefinedType[str]):
    """The column type of the ltree extension (kept here so the migration stays frozen)."""

    cache_ok = True

    def get_col_spec(self, **kw: Any) -> str:
        return "LTREE"


_UNIT_STATUSES = "'labeled', 'in_stock', 'allocated', 'picked', 'shipped', 'scrapped'"


def upgrade() -> None:
    op.add_column(
        "outbox",
        sa.Column(
            "handled_by",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        schema="platform",
    )
    _add_lead_times()
    op.execute("CREATE EXTENSION IF NOT EXISTS ltree")
    op.execute("CREATE SCHEMA inventory")
    _create_locations()
    _create_allocations()
    _create_units()
    _create_scans()
    _create_stock_ledger()


def _add_lead_times() -> None:
    for column in ("lead_time_min_weeks", "lead_time_max_weeks"):
        op.add_column(
            "variants", sa.Column(column, sa.SmallInteger(), nullable=True), schema="catalog"
        )
    op.execute(
        "UPDATE catalog.variants SET lead_time_min_weeks = 4, lead_time_max_weeks = 6 "
        "WHERE allow_backorder"
    )
    op.create_check_constraint(
        "ck_variants_lead_time_pair",
        "variants",
        "(lead_time_min_weeks IS NULL) = (lead_time_max_weeks IS NULL)",
        schema="catalog",
    )
    op.create_check_constraint(
        "ck_variants_lead_time_range",
        "variants",
        "lead_time_min_weeks IS NULL OR (lead_time_min_weeks BETWEEN 1 AND 52 "
        "AND lead_time_max_weeks BETWEEN lead_time_min_weeks AND 52)",
        schema="catalog",
    )
    # Made to order means a lead time.
    op.create_check_constraint(
        "ck_variants_made_to_order_lead_time",
        "variants",
        "NOT allow_backorder OR lead_time_min_weeks IS NOT NULL",
        schema="catalog",
    )


def _timestamps() -> list[sa.Column[object]]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    ]


def _create_locations() -> None:
    op.create_table(
        "locations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("parent_id", sa.Uuid(), nullable=True),
        # Printed on the label: unique, upper case, never changed.
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("path", _Ltree(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False, server_default=_EMPTY),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_locations"),
        sa.UniqueConstraint("code", name="uq_locations_code"),
        sa.UniqueConstraint("path", name="uq_locations_path"),
        sa.ForeignKeyConstraint(
            ["parent_id"],
            ["inventory.locations.id"],
            name="fk_locations_parent_id_locations",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "kind IN ('site', 'shelf', 'compartment', 'box', 'staging')", name="ck_locations_kind"
        ),
        sa.CheckConstraint(
            "code ~ '^[A-Z0-9]{1,8}(-[A-Z0-9]{1,8}){0,4}$'", name="ck_locations_code_format"
        ),
        # Only a site stands on its own; everything else lies somewhere.
        sa.CheckConstraint(
            "(kind = 'site') = (parent_id IS NULL)", name="ck_locations_site_is_root"
        ),
        schema="inventory",
    )
    op.create_index(
        "locations_path_idx", "locations", ["path"], schema="inventory", postgresql_using="gist"
    )
    op.create_index("locations_parent_idx", "locations", ["parent_id"], schema="inventory")


def _create_allocations() -> None:
    op.create_table(
        "allocations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("order_id", sa.Uuid(), nullable=False),
        # The order line and variant are named without a key, like sales does.
        sa.Column("order_line_id", sa.Uuid(), nullable=False),
        sa.Column("variant_id", sa.Uuid(), nullable=False),
        sa.Column("piece", sa.SmallInteger(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_allocations"),
        sa.ForeignKeyConstraint(
            ["order_id"],
            ["sales.orders.id"],
            name="fk_allocations_order_id_orders",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("order_line_id", "piece", name="uq_allocations_order_line_id_piece"),
        sa.CheckConstraint(
            "status IN ('open', 'shipped', 'released')", name="ck_allocations_status"
        ),
        sa.CheckConstraint("piece >= 0", name="ck_allocations_piece_non_negative"),
        schema="inventory",
    )
    op.create_index("allocations_order_idx", "allocations", ["order_id"], schema="inventory")
    # Backorders are served first come, first served.
    op.create_index(
        "allocations_open_idx",
        "allocations",
        ["variant_id", "created_at"],
        schema="inventory",
        postgresql_where=sa.text("status = 'open'"),
    )


def _create_units() -> None:
    op.create_table(
        "units",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("variant_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("location_id", sa.Uuid(), nullable=True),
        sa.Column("allocation_id", sa.Uuid(), nullable=True),
        sa.Column("scrap_note", sa.Text(), nullable=False, server_default=_EMPTY),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_units"),
        sa.UniqueConstraint("code", name="uq_units_code"),
        # One unit per allocation, checked at commit: handing an allocation from one
        # unit to another is a single step.
        sa.UniqueConstraint(
            "allocation_id", name="uq_units_allocation_id", deferrable=True, initially="DEFERRED"
        ),
        # A variant that ever had a unit keeps existing; it can be deactivated.
        sa.ForeignKeyConstraint(
            ["variant_id"],
            ["catalog.variants.id"],
            name="fk_units_variant_id_variants",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["location_id"],
            ["inventory.locations.id"],
            name="fk_units_location_id_locations",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["allocation_id"],
            ["inventory.allocations.id"],
            name="fk_units_allocation_id_allocations",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(f"status IN ({_UNIT_STATUSES})", name="ck_units_status"),
        # Crockford Base32: no I, L, O or U.
        sa.CheckConstraint("code ~ '^[0-9A-HJKMNP-TV-Z]{10}$'", name="ck_units_code_format"),
        sa.CheckConstraint(
            "(status IN ('in_stock', 'allocated')) = (location_id IS NOT NULL)",
            name="ck_units_on_shelf",
        ),
        sa.CheckConstraint(
            "(status IN ('allocated', 'picked', 'shipped')) = (allocation_id IS NOT NULL)",
            name="ck_units_serves_allocation",
        ),
        schema="inventory",
    )
    op.create_index(
        "units_variant_status_idx",
        "units",
        ["variant_id", "status", "created_at"],
        schema="inventory",
    )
    op.create_index(
        "units_location_idx",
        "units",
        ["location_id"],
        schema="inventory",
        postgresql_where=sa.text("location_id IS NOT NULL"),
    )


def _create_scans() -> None:
    op.create_table(
        "scans",
        # Generated by the device: a scan sent again is recognised by it.
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("staff_id", sa.Uuid(), nullable=False),
        sa.Column("mode", sa.Text(), nullable=False),
        sa.Column("raw", sa.Text(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column(
            "context",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("outcome", sa.Text(), nullable=False),
        # The answer given; a repeated request gets it again without booking anything.
        sa.Column("response", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("undone_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_scans"),
        sa.ForeignKeyConstraint(
            ["staff_id"],
            ["identity.accounts.id"],
            name="fk_scans_staff_id_accounts",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint("mode IN ('put_away', 'pick', 'lookup')", name="ck_scans_mode"),
        sa.CheckConstraint(
            "outcome IN ('applied', 'selected', 'info', 'rejected', 'unknown')",
            name="ck_scans_outcome",
        ),
        sa.CheckConstraint("source IN ('camera', 'scanner', 'keyboard')", name="ck_scans_source"),
        sa.CheckConstraint("length(raw) BETWEEN 1 AND 300", name="ck_scans_raw_length"),
        sa.CheckConstraint(
            "undone_at IS NULL OR outcome = 'applied'", name="ck_scans_undo_needs_booking"
        ),
        schema="inventory",
    )
    op.create_index("scans_staff_idx", "scans", ["staff_id", "created_at"], schema="inventory")


def _create_stock_ledger() -> None:
    op.create_table(
        "stock_ledger",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("unit_id", sa.Uuid(), nullable=False),
        sa.Column("variant_id", sa.Uuid(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("from_status", sa.Text(), nullable=True),
        sa.Column("to_status", sa.Text(), nullable=False),
        sa.Column("from_location_id", sa.Uuid(), nullable=True),
        sa.Column("to_location_id", sa.Uuid(), nullable=True),
        sa.Column("allocation_id", sa.Uuid(), nullable=True),
        sa.Column("scan_id", sa.Uuid(), nullable=True),
        sa.Column("staff_id", sa.Uuid(), nullable=True),
        # An undo books the movement backwards and names the entry it reverses, once.
        sa.Column("reverses_id", sa.BigInteger(), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_stock_ledger"),
        sa.UniqueConstraint("reverses_id", name="uq_stock_ledger_reverses_id"),
        *(
            sa.ForeignKeyConstraint(
                [column],
                [target],
                name=f"fk_stock_ledger_{column}_{target.split('.')[1]}",
                ondelete="RESTRICT",
            )
            for column, target in (
                ("unit_id", "inventory.units.id"),
                ("from_location_id", "inventory.locations.id"),
                ("to_location_id", "inventory.locations.id"),
                ("allocation_id", "inventory.allocations.id"),
                ("scan_id", "inventory.scans.id"),
                ("staff_id", "identity.accounts.id"),
                ("reverses_id", "inventory.stock_ledger.id"),
            )
        ),
        sa.CheckConstraint(
            "reason IN ('label', 'put_away', 'move', 'allocate', 'release', 'pick', 'ship', "
            "'scrap', 'undo')",
            name="ck_stock_ledger_reason",
        ),
        sa.CheckConstraint(
            f"(from_status IS NULL OR from_status IN ({_UNIT_STATUSES})) "
            f"AND to_status IN ({_UNIT_STATUSES})",
            name="ck_stock_ledger_statuses",
        ),
        # Only labelling starts a unit's history; every later entry knows where it came from.
        sa.CheckConstraint(
            "(reason = 'label') = (from_status IS NULL)", name="ck_stock_ledger_label_starts"
        ),
        sa.CheckConstraint(
            "(reason = 'undo') = (reverses_id IS NOT NULL)", name="ck_stock_ledger_undo_reverses"
        ),
        schema="inventory",
    )
    op.create_index("stock_ledger_unit_idx", "stock_ledger", ["unit_id", "id"], schema="inventory")
    op.create_index(
        "stock_ledger_scan_idx",
        "stock_ledger",
        ["scan_id"],
        schema="inventory",
        postgresql_where=sa.text("scan_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_table("stock_ledger", schema="inventory")
    op.drop_table("scans", schema="inventory")
    op.drop_table("units", schema="inventory")
    op.drop_table("allocations", schema="inventory")
    op.drop_table("locations", schema="inventory")
    op.execute("DROP SCHEMA inventory")
    # The ltree extension stays, like citext: it belongs to the database.
    op.drop_column("outbox", "handled_by", schema="platform")
    for name in ("made_to_order_lead_time", "lead_time_range", "lead_time_pair"):
        op.drop_constraint(f"ck_variants_{name}", "variants", schema="catalog", type_="check")
    for column in ("lead_time_max_weeks", "lead_time_min_weeks"):
        op.drop_column("variants", column, schema="catalog")
