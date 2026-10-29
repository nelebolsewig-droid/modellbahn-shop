"""Marketplace: eBay's notifications of closed accounts (ADR 0015).

- ``marketplace.marketplace_orders.buyer_erased_at``: when the buyer's personal data went.
- An index on the buyer's user name (ignoring case): every notification looks it up, and
  nearly all of them name nobody who bought here.

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "marketplace_orders",
        sa.Column("buyer_erased_at", sa.DateTime(timezone=True)),
        schema="marketplace",
    )
    op.create_index(
        "marketplace_orders_buyer_idx",
        "marketplace_orders",
        ["channel", sa.text("lower(buyer_name)")],
        schema="marketplace",
        postgresql_where=sa.text("buyer_erased_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "marketplace_orders_buyer_idx", table_name="marketplace_orders", schema="marketplace"
    )
    op.drop_column("marketplace_orders", "buyer_erased_at", schema="marketplace")
