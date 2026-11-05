"""Refunds after a return and cancellations on withdrawal (ADR 0020).

Written by hand like the migrations before; constraint names follow the naming
convention of ``modellbahn.platform.db``.

- ``sales.payments.refunded_cents``: what went back so far; refunded payments count in full.
- ``sales.orders.cancel_reason`` may be ``withdrawn``: the customer withdrew before dispatch.

Revision ID: 0014
Revises: 0013
Create Date: 2026-11-04
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_REASONS_BEFORE = "cancel_reason IN ('payment_timeout', 'by_shop', 'by_marketplace')"
_REASONS_AFTER = "cancel_reason IN ('payment_timeout', 'by_shop', 'by_marketplace', 'withdrawn')"


def upgrade() -> None:
    op.add_column(
        "payments",
        sa.Column("refunded_cents", sa.Integer(), server_default=sa.text("0"), nullable=False),
        schema="sales",
    )
    op.execute("UPDATE sales.payments SET refunded_cents = amount_cents WHERE status = 'refunded'")
    op.create_check_constraint(
        "ck_payments_refunded_cents_range",
        "payments",
        "refunded_cents >= 0 AND refunded_cents <= amount_cents",
        schema="sales",
    )
    op.create_check_constraint(
        "ck_payments_refunded_in_full",
        "payments",
        "status <> 'refunded' OR refunded_cents = amount_cents",
        schema="sales",
    )
    op.drop_constraint("ck_orders_cancel_reason", "orders", schema="sales", type_="check")
    op.create_check_constraint(
        "ck_orders_cancel_reason",
        "orders",
        f"cancel_reason IS NULL OR {_REASONS_AFTER}",
        schema="sales",
    )


def downgrade() -> None:
    # Orders cancelled on withdrawal count as cancelled by the shop in the older model.
    op.execute(
        "UPDATE sales.orders SET cancel_reason = 'by_shop' WHERE cancel_reason = 'withdrawn'"
    )
    op.drop_constraint("ck_orders_cancel_reason", "orders", schema="sales", type_="check")
    op.create_check_constraint(
        "ck_orders_cancel_reason",
        "orders",
        f"cancel_reason IS NULL OR {_REASONS_BEFORE}",
        schema="sales",
    )
    op.drop_constraint("ck_payments_refunded_in_full", "payments", schema="sales", type_="check")
    op.drop_constraint(
        "ck_payments_refunded_cents_range", "payments", schema="sales", type_="check"
    )
    op.drop_column("payments", "refunded_cents", schema="sales")
