"""The till: sales rung up in the SumUp app book pieces out by themselves (ADR 0041).

Written by hand like the migrations before.

- ``inventory.till_state``: one row, where fetching the till's sales stands (since when,
  last run, last error).
- ``inventory.till_items``: a name in the SumUp app and the variant it sells, or that it
  is no model at all (ignored).
- ``inventory.till_lines``: every line of every till sale fetched, with how many of its
  pieces were booked out and what is still to do.

Revision ID: 0029
Revises: 0028
Create Date: 2026-11-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0029"
down_revision: str | None = "0028"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_STATES = "'booked', 'unassigned', 'custom', 'short', 'ignored', 'done'"


def upgrade() -> None:
    op.create_table(
        "till_state",
        sa.Column("id", sa.SmallInteger(), nullable=False),
        sa.Column("since", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_sync_at", sa.DateTime(timezone=True)),
        sa.Column("last_error", sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.CheckConstraint("id = 1", name="ck_till_state_single_row"),
        sa.PrimaryKeyConstraint("id", name="pk_till_state"),
        schema="inventory",
    )
    op.create_table(
        "till_items",
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("variant_id", sa.Uuid()),
        sa.Column("ignored", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("assigned_by", sa.Uuid()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "NOT (ignored AND variant_id IS NOT NULL)", name="ck_till_items_variant_or_ignored"
        ),
        sa.ForeignKeyConstraint(
            ["variant_id"],
            ["catalog.variants.id"],
            name="fk_till_items_variant_id_variants",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["assigned_by"],
            ["identity.accounts.id"],
            name="fk_till_items_assigned_by_accounts",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("key", name="pk_till_items"),
        schema="inventory",
    )
    op.create_table(
        "till_lines",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("transaction_code", sa.Text(), nullable=False),
        sa.Column("position", sa.SmallInteger(), nullable=False),
        sa.Column("sold_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payment", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("unit_price_cents", sa.Integer(), nullable=False),
        sa.Column("booked", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("state", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("payment IN ('card', 'cash')", name="ck_till_lines_payment"),
        sa.CheckConstraint(f"state IN ({_STATES})", name="ck_till_lines_state"),
        sa.CheckConstraint("quantity BETWEEN 1 AND 999", name="ck_till_lines_quantity_range"),
        sa.CheckConstraint("unit_price_cents >= 0", name="ck_till_lines_price_not_negative"),
        sa.CheckConstraint("booked BETWEEN 0 AND quantity", name="ck_till_lines_booked_range"),
        sa.PrimaryKeyConstraint("id", name="pk_till_lines"),
        sa.UniqueConstraint(
            "transaction_code", "position", name="uq_till_lines_transaction_code_position"
        ),
        schema="inventory",
    )
    op.create_index(
        "till_lines_open_idx",
        "till_lines",
        ["key"],
        schema="inventory",
        postgresql_where=sa.text("state IN ('unassigned', 'custom', 'short')"),
    )
    op.create_index("till_lines_sold_at_idx", "till_lines", ["sold_at"], schema="inventory")


def downgrade() -> None:
    op.drop_index("till_lines_sold_at_idx", table_name="till_lines", schema="inventory")
    op.drop_index("till_lines_open_idx", table_name="till_lines", schema="inventory")
    op.drop_table("till_lines", schema="inventory")
    op.drop_table("till_items", schema="inventory")
    op.drop_table("till_state", schema="inventory")
