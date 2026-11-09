"""Payment in advance by bank transfer (ADR 0022).

Written by hand like the migrations before; constraint names follow the naming
convention of ``modellbahn.platform.db``.

- A pending payment of the provider ``bank_transfer`` waits for the money in the shop's
  account, not on a provider's page: it has no ``checkout_url``.

Revision ID: 0015
Revises: 0014
Create Date: 2026-11-09
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("ck_payments_checkout_url", "payments", schema="sales")
    op.create_check_constraint(
        "ck_payments_checkout_url",
        "payments",
        "(status = 'pending' AND provider <> 'bank_transfer') = (checkout_url IS NOT NULL)",
        schema="sales",
    )


def downgrade() -> None:
    # Transfers still awaited have no place in the older model: they count as failed.
    op.execute(
        "UPDATE sales.payments SET status = 'failed', failure_code = 'expired' "
        "WHERE status = 'pending' AND provider = 'bank_transfer'"
    )
    op.drop_constraint("ck_payments_checkout_url", "payments", schema="sales")
    op.create_check_constraint(
        "ck_payments_checkout_url",
        "payments",
        "(status = 'pending') = (checkout_url IS NOT NULL)",
        schema="sales",
    )
