"""Declarations of withdrawal from the shop's withdrawal function (§ 356a BGB, ADR 0020).

Written by hand like the migrations before; constraint names follow the naming
convention of ``modellbahn.platform.db``.

- ``sales.withdrawals`` keeps each declaration as it came in, with the time of receipt.
- ``order_id`` names the order when number and e-mail address fit one.

Revision ID: 0013
Revises: 0012
Create Date: 2026-11-04
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "withdrawals",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("order_reference", sa.Text(), nullable=False),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("scope", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column("order_id", sa.Uuid(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_withdrawals"),
        sa.ForeignKeyConstraint(
            ["order_id"],
            ["sales.orders.id"],
            name="fk_withdrawals_order_id_orders",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint("name <> ''", name="ck_withdrawals_name_not_empty"),
        sa.CheckConstraint(
            "order_reference <> ''", name="ck_withdrawals_order_reference_not_empty"
        ),
        schema="sales",
    )
    op.create_index("withdrawals_received_idx", "withdrawals", ["received_at"], schema="sales")
    op.create_index("withdrawals_order_idx", "withdrawals", ["order_id"], schema="sales")


def downgrade() -> None:
    op.drop_index("withdrawals_order_idx", table_name="withdrawals", schema="sales")
    op.drop_index("withdrawals_received_idx", table_name="withdrawals", schema="sales")
    op.drop_table("withdrawals", schema="sales")
