"""The workshop's automation (ADR 0034).

Written by hand like the migrations before.

``sales.daily_digests``: one row per day the morning mail „Heute dran“ went out, so
several workers send it once.

``sales.orders.making_started_at``: when the first plate for one of the order's pieces
went on a printer. The customer hears so once, and the order page shows it. Empty for
orders that ship from the shelves and for orders placed before.

Revision ID: 0023
Revises: 0022
Create Date: 2026-11-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0023"
down_revision: str | None = "0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "orders", sa.Column("making_started_at", sa.DateTime(timezone=True)), schema="sales"
    )
    op.create_table(
        "daily_digests",
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("day", name="pk_daily_digests"),
        schema="sales",
    )


def downgrade() -> None:
    op.drop_table("daily_digests", schema="sales")
    op.drop_column("orders", "making_started_at", schema="sales")
