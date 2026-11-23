"""Note when an order made for the customer goes into painting and assembly (ADR 0046).

Written by hand like the migrations before.

- ``sales.orders.finishing_started_at``: when the staff pressed „Lackierung & Montage“;
  the customer hears it once.

Revision ID: 0033
Revises: 0032
Create Date: 2026-11-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0033"
down_revision: str | None = "0032"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "orders",
        sa.Column("finishing_started_at", sa.DateTime(timezone=True)),
        schema="sales",
    )


def downgrade() -> None:
    op.drop_column("orders", "finishing_started_at", schema="sales")
