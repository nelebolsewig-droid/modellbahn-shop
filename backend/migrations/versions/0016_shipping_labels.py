"""Shipping labels booked with DHL from the Stellwerk (ADR 0023).

Written by hand like the migrations before; constraint names follow the naming
convention of ``modellbahn.platform.db``.

- ``sales.shipping_labels`` keeps each label with the carrier's shipment number and the
  PDF to print; a cancelled one stays for the record. One label per order is in force.

Revision ID: 0016
Revises: 0015
Create Date: 2026-11-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "shipping_labels",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("order_id", sa.Uuid(), nullable=False),
        sa.Column("carrier", sa.Text(), nullable=False),
        sa.Column("product", sa.Text(), nullable=False),
        sa.Column("shipment_number", sa.Text(), nullable=False),
        sa.Column("weight_g", sa.Integer(), nullable=False),
        sa.Column("print_format", sa.Text(), nullable=False),
        sa.Column("document", sa.LargeBinary(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_shipping_labels"),
        sa.ForeignKeyConstraint(
            ["order_id"],
            ["sales.orders.id"],
            name="fk_shipping_labels_order_id_orders",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint("product IN ('V01PAK', 'V53WPAK')", name="ck_shipping_labels_product"),
        sa.CheckConstraint("status IN ('active', 'cancelled')", name="ck_shipping_labels_status"),
        sa.CheckConstraint(
            "shipment_number <> ''", name="ck_shipping_labels_shipment_number_not_empty"
        ),
        sa.CheckConstraint("weight_g BETWEEN 10 AND 31500", name="ck_shipping_labels_weight_range"),
        sa.CheckConstraint(
            "(status = 'cancelled') = (cancelled_at IS NOT NULL)",
            name="ck_shipping_labels_cancelled_at",
        ),
        schema="sales",
    )
    op.create_index(
        "shipping_labels_one_active_idx",
        "shipping_labels",
        ["order_id"],
        unique=True,
        schema="sales",
        postgresql_where=sa.text("status = 'active'"),
    )
    op.create_index(
        "shipping_labels_order_idx",
        "shipping_labels",
        ["order_id", "created_at"],
        schema="sales",
    )


def downgrade() -> None:
    op.drop_index("shipping_labels_order_idx", table_name="shipping_labels", schema="sales")
    op.drop_index("shipping_labels_one_active_idx", table_name="shipping_labels", schema="sales")
    op.drop_table("shipping_labels", schema="sales")
