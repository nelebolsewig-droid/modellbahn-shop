"""Parts store: printed parts by the box, receipts of finished plates, the parts journal.

Written by hand like the migrations before; constraint names follow the naming
convention of ``modellbahn.platform.db``.

- ``inventory.part_stock``: how many of a part lie in a location.
- ``inventory.part_receipts``: the good parts of one part from one finished plate, until
  they are in a box (Wareneingang).
- ``inventory.part_ledger``: every change of a quantity, for good; an assembly names
  the unit it made.

Revision ID: 0011
Revises: 0010
Create Date: 2026-10-30
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_EMPTY = sa.text("''")


def upgrade() -> None:
    _create_part_stock()
    _create_part_receipts()
    _create_part_ledger()


def _create_part_stock() -> None:
    op.create_table(
        "part_stock",
        sa.Column("part_id", sa.Uuid(), nullable=False),
        sa.Column("location_id", sa.Uuid(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("part_id", "location_id", name="pk_part_stock"),
        sa.ForeignKeyConstraint(
            ["part_id"],
            ["manufacturing.parts.id"],
            name="fk_part_stock_part_id_parts",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["location_id"],
            ["inventory.locations.id"],
            name="fk_part_stock_location_id_locations",
            ondelete="RESTRICT",
        ),
        # An emptied box keeps its row at 0 until something goes in again.
        sa.CheckConstraint("quantity >= 0", name="ck_part_stock_quantity_non_negative"),
        schema="inventory",
    )
    op.create_index("part_stock_location_idx", "part_stock", ["location_id"], schema="inventory")


def _create_part_receipts() -> None:
    op.create_table(
        "part_receipts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("print_job_id", sa.Uuid(), nullable=False),
        sa.Column("part_id", sa.Uuid(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("stored", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("written_off", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_part_receipts"),
        # The parts came off a line of that plate; a plate yields one receipt per part.
        sa.ForeignKeyConstraint(
            ["print_job_id", "part_id"],
            ["manufacturing.print_job_lines.job_id", "manufacturing.print_job_lines.part_id"],
            name="fk_part_receipts_print_job_id_part_id_print_job_lines",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "print_job_id", "part_id", name="uq_part_receipts_print_job_id_part_id"
        ),
        sa.CheckConstraint("quantity > 0", name="ck_part_receipts_quantity_positive"),
        sa.CheckConstraint(
            "stored >= 0 AND written_off >= 0", name="ck_part_receipts_counts_non_negative"
        ),
        # Never more parts stored and written off than came off the plate.
        sa.CheckConstraint(
            "stored + written_off <= quantity", name="ck_part_receipts_counts_within_quantity"
        ),
        schema="inventory",
    )
    # The receiving area: what still waits for a box, first come first served.
    op.create_index(
        "part_receipts_open_idx",
        "part_receipts",
        ["part_id", "created_at"],
        schema="inventory",
        postgresql_where=sa.text("stored + written_off < quantity"),
    )


def _create_part_ledger() -> None:
    op.create_table(
        "part_ledger",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("part_id", sa.Uuid(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("from_location_id", sa.Uuid(), nullable=True),
        sa.Column("to_location_id", sa.Uuid(), nullable=True),
        sa.Column("receipt_id", sa.Uuid(), nullable=True),
        # The unit an assembly made: every kit knows the boxes its parts came from.
        sa.Column("unit_id", sa.Uuid(), nullable=True),
        sa.Column("note", sa.Text(), server_default=_EMPTY, nullable=False),
        sa.Column("scan_id", sa.Uuid(), nullable=True),
        sa.Column("staff_id", sa.Uuid(), nullable=True),
        sa.Column("reverses_id", sa.BigInteger(), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_part_ledger"),
        sa.UniqueConstraint("reverses_id", name="uq_part_ledger_reverses_id"),
        *(
            sa.ForeignKeyConstraint(
                [column],
                [target],
                name=f"fk_part_ledger_{column}_{target.split('.')[1]}",
                ondelete="RESTRICT",
            )
            for column, target in (
                ("part_id", "manufacturing.parts.id"),
                ("from_location_id", "inventory.locations.id"),
                ("to_location_id", "inventory.locations.id"),
                ("receipt_id", "inventory.part_receipts.id"),
                ("unit_id", "inventory.units.id"),
                ("scan_id", "inventory.scans.id"),
                ("staff_id", "identity.accounts.id"),
                ("reverses_id", "inventory.part_ledger.id"),
            )
        ),
        sa.CheckConstraint(
            "reason IN ('receive', 'assemble', 'count', 'write_off', 'undo')",
            name="ck_part_ledger_reason",
        ),
        sa.CheckConstraint("quantity > 0", name="ck_part_ledger_quantity_positive"),
        # Where each kind of movement comes from and goes to.
        sa.CheckConstraint(
            "CASE reason "
            "WHEN 'receive' THEN receipt_id IS NOT NULL "
            "AND from_location_id IS NULL AND to_location_id IS NOT NULL "
            "WHEN 'assemble' THEN unit_id IS NOT NULL "
            "AND from_location_id IS NOT NULL AND to_location_id IS NULL "
            "WHEN 'count' THEN (from_location_id IS NULL) <> (to_location_id IS NULL) "
            "WHEN 'write_off' THEN receipt_id IS NOT NULL "
            "AND from_location_id IS NULL AND to_location_id IS NULL "
            "ELSE from_location_id IS DISTINCT FROM to_location_id END",
            name="ck_part_ledger_shape",
        ),
        sa.CheckConstraint(
            "unit_id IS NULL OR reason = 'assemble'", name="ck_part_ledger_unit_for_assembly"
        ),
        sa.CheckConstraint(
            "(reason = 'undo') = (reverses_id IS NOT NULL)", name="ck_part_ledger_undo_reverses"
        ),
        schema="inventory",
    )
    op.create_index("part_ledger_part_idx", "part_ledger", ["part_id", "id"], schema="inventory")
    op.create_index(
        "part_ledger_unit_idx",
        "part_ledger",
        ["unit_id"],
        schema="inventory",
        postgresql_where=sa.text("unit_id IS NOT NULL"),
    )
    op.create_index(
        "part_ledger_scan_idx",
        "part_ledger",
        ["scan_id"],
        schema="inventory",
        postgresql_where=sa.text("scan_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_table("part_ledger", schema="inventory")
    op.drop_table("part_receipts", schema="inventory")
    op.drop_table("part_stock", schema="inventory")
