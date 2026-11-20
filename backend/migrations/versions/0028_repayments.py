"""Repayments of bank transfers: what went back by transfer, and to which account (ADR 0040).

Written by hand like the migrations before; constraint names follow the naming
convention of ``modellbahn.platform.db``.

- ``sales.payments.repaid_cents``: of a bank transfer's refunds, what the staff have
  transferred back. Refunds of transfers made before this migration count as open, so
  the Stellwerk lists them until somebody marks them as transferred.
- ``sales.payments.repay_holder`` / ``repay_iban``: the account an open repayment goes
  to, typed in from the bank statement; cleared once it is repaid.

Revision ID: 0028
Revises: 0027
Create Date: 2026-11-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0028"
down_revision: str | None = "0027"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "payments",
        sa.Column("repaid_cents", sa.Integer(), server_default=sa.text("0"), nullable=False),
        schema="sales",
    )
    op.add_column("payments", sa.Column("repay_holder", sa.Text()), schema="sales")
    op.add_column("payments", sa.Column("repay_iban", sa.Text()), schema="sales")
    op.create_check_constraint(
        "ck_payments_repaid_cents_range",
        "payments",
        "repaid_cents >= 0 AND repaid_cents <= refunded_cents",
        schema="sales",
    )
    op.create_check_constraint(
        "ck_payments_repay_account_complete",
        "payments",
        "(repay_holder IS NULL) = (repay_iban IS NULL)",
        schema="sales",
    )


def downgrade() -> None:
    for name in ("repay_account_complete", "repaid_cents_range"):
        op.drop_constraint(f"ck_payments_{name}", "payments", schema="sales", type_="check")
    for column in ("repay_iban", "repay_holder", "repaid_cents"):
        op.drop_column("payments", column, schema="sales")
