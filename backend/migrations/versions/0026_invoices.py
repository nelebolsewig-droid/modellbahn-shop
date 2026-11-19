"""Invoices and invoice corrections for shipped orders (ADR 0038).

Written by hand like the migrations before; constraint names follow the naming
convention of ``modellbahn.platform.db``.

- ``sales.invoices`` keeps each issued invoice (``RE-…``) and correction (``RK-…``) with
  its PDF, as the customer received it. One invoice per order; a correction per refund.
- ``sales.invoice_counters`` holds the last number of each series and year, so the
  numbers run without gaps.

Revision ID: 0026
Revises: 0025
Create Date: 2026-11-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0026"
down_revision: str | None = "0025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "invoices",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("order_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("number", sa.Text(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("total_cents", sa.Integer(), nullable=False),
        sa.Column("tax_cents", sa.Integer(), nullable=False),
        sa.Column("document", sa.LargeBinary(), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("corrects_id", sa.Uuid(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_invoices"),
        sa.UniqueConstraint("number", name="uq_invoices_number"),
        sa.ForeignKeyConstraint(
            ["order_id"],
            ["sales.orders.id"],
            name="fk_invoices_order_id_orders",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["corrects_id"],
            ["sales.invoices.id"],
            name="fk_invoices_corrects_id_invoices",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint("kind IN ('invoice', 'correction')", name="ck_invoices_kind"),
        sa.CheckConstraint(
            "number ~ '^(RE|RK)-[0-9]{4}-[0-9]{5,}$'", name="ck_invoices_number_format"
        ),
        sa.CheckConstraint(
            "(kind = 'invoice') = (corrects_id IS NULL)",
            name="ck_invoices_correction_names_invoice",
        ),
        sa.CheckConstraint(
            "(kind = 'invoice' AND total_cents >= 0) OR (kind = 'correction' AND total_cents < 0)",
            name="ck_invoices_total_sign",
        ),
        schema="sales",
    )
    op.create_index(
        "invoices_order_source_idx",
        "invoices",
        ["order_id", "source"],
        unique=True,
        schema="sales",
    )
    op.create_table(
        "invoice_counters",
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("year", sa.SmallInteger(), nullable=False),
        sa.Column("last_serial", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("kind", "year", name="pk_invoice_counters"),
        sa.CheckConstraint("kind IN ('invoice', 'correction')", name="ck_invoice_counters_kind"),
        sa.CheckConstraint("last_serial > 0", name="ck_invoice_counters_last_serial_positive"),
        schema="sales",
    )


def downgrade() -> None:
    op.drop_table("invoice_counters", schema="sales")
    op.drop_index("invoices_order_source_idx", table_name="invoices", schema="sales")
    op.drop_table("invoices", schema="sales")
