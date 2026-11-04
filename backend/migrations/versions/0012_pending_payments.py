"""Payments on the provider's page: pending payments with their page and transaction (ADR 0019).

Written by hand like the migrations before; constraint names follow the naming
convention of ``modellbahn.platform.db``.

- ``sales.payments.status`` may be ``pending``: the customer pays on SumUp's page.
- ``checkout_url`` is that page, set exactly while the payment is pending.
- ``transaction_ref`` names SumUp's transaction, which a refund needs.
- At most one pending payment per order.

Revision ID: 0012
Revises: 0011
Create Date: 2026-11-04
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("payments", sa.Column("checkout_url", sa.Text(), nullable=True), schema="sales")
    op.add_column(
        "payments", sa.Column("transaction_ref", sa.Text(), nullable=True), schema="sales"
    )
    op.drop_constraint("ck_payments_status", "payments", schema="sales")
    op.create_check_constraint(
        "ck_payments_status",
        "payments",
        "status IN ('pending', 'captured', 'failed', 'refunded')",
        schema="sales",
    )
    op.create_check_constraint(
        "ck_payments_checkout_url",
        "payments",
        "(status = 'pending') = (checkout_url IS NOT NULL)",
        schema="sales",
    )
    op.create_index(
        "payments_one_pending_idx",
        "payments",
        ["order_id"],
        unique=True,
        schema="sales",
        postgresql_where=sa.text("status = 'pending'"),
    )


def downgrade() -> None:
    op.drop_index("payments_one_pending_idx", table_name="payments", schema="sales")
    op.drop_constraint("ck_payments_checkout_url", "payments", schema="sales")
    # Pending payments have no place in the older model: they count as failed.
    op.execute(
        "UPDATE sales.payments SET status = 'failed', failure_code = 'expired' "
        "WHERE status = 'pending'"
    )
    op.drop_constraint("ck_payments_status", "payments", schema="sales")
    op.create_check_constraint(
        "ck_payments_status",
        "payments",
        "status IN ('captured', 'failed', 'refunded')",
        schema="sales",
    )
    op.drop_column("payments", "transaction_ref", schema="sales")
    op.drop_column("payments", "checkout_url", schema="sales")
