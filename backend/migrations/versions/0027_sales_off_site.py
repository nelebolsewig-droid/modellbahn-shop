"""What a piece sold outside the online shop brought in: channel and price (ADR 0039).

Written by hand like the migrations before.

- ``inventory.units.sale_channel``: fair, store, private or other; only for a unit booked
  out as sold. Empty for pieces sold before, until somebody enters it afterwards.
- ``inventory.units.sale_price_cents``: the gross price it was sold for; empty while
  unknown, then the sales report counts the shop price.

Revision ID: 0027
Revises: 0026
Create Date: 2026-11-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0027"
down_revision: str | None = "0026"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("units", sa.Column("sale_channel", sa.Text()), schema="inventory")
    op.add_column("units", sa.Column("sale_price_cents", sa.Integer()), schema="inventory")
    op.create_check_constraint(
        "ck_units_sale_channel",
        "units",
        "sale_channel IN ('fair', 'store', 'private', 'other')",
        schema="inventory",
    )
    op.create_check_constraint(
        "ck_units_sale_price_range",
        "units",
        "sale_price_cents BETWEEN 0 AND 10000000",
        schema="inventory",
    )
    op.create_check_constraint(
        "ck_units_sale_when_sold",
        "units",
        "(sale_channel IS NULL AND sale_price_cents IS NULL) OR scrap_reason = 'sold'",
        schema="inventory",
    )


def downgrade() -> None:
    for name in ("sale_when_sold", "sale_price_range", "sale_channel"):
        op.drop_constraint(f"ck_units_{name}", "units", schema="inventory", type_="check")
    op.drop_column("units", "sale_price_cents", schema="inventory")
    op.drop_column("units", "sale_channel", schema="inventory")
