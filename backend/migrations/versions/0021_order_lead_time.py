"""An order keeps the lead time its checkout showed (ADR 0029).

Written by hand like the migrations before; constraint names follow the naming
convention of ``modellbahn.platform.db``.

``sales.orders.lead_time_min_weeks`` and ``lead_time_max_weeks``: when some pieces are
made for the customer, the weeks the checkout promised for the parcel, so the e-mails
can say when it ships. Empty when everything ships from the shelves, and for orders
placed before.

Revision ID: 0021
Revises: 0020
Create Date: 2026-11-16
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0021"
down_revision: str | None = "0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("orders", sa.Column("lead_time_min_weeks", sa.SmallInteger()), schema="sales")
    op.add_column("orders", sa.Column("lead_time_max_weeks", sa.SmallInteger()), schema="sales")
    op.create_check_constraint(
        "ck_orders_lead_time_pair",
        "orders",
        "(lead_time_min_weeks IS NULL) = (lead_time_max_weeks IS NULL)",
        schema="sales",
    )
    op.create_check_constraint(
        "ck_orders_lead_time_range",
        "orders",
        "lead_time_min_weeks IS NULL OR (lead_time_min_weeks BETWEEN 1 AND 52 "
        "AND lead_time_max_weeks BETWEEN lead_time_min_weeks AND 52)",
        schema="sales",
    )


def downgrade() -> None:
    op.drop_constraint("ck_orders_lead_time_range", "orders", schema="sales", type_="check")
    op.drop_constraint("ck_orders_lead_time_pair", "orders", schema="sales", type_="check")
    op.drop_column("orders", "lead_time_max_weeks", schema="sales")
    op.drop_column("orders", "lead_time_min_weeks", schema="sales")
