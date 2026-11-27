"""A label per product: adp itself or a partner (Vehicle World, MilMod), for the shop filter.

Written by hand like the migrations before. Every existing product is adp's own.

Revision ID: 0036
Revises: 0035
Create Date: 2026-11-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0036"
down_revision: str | None = "0035"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "products",
        sa.Column("label", sa.Text(), server_default=sa.text("'adp'"), nullable=False),
        schema="catalog",
    )
    op.create_check_constraint(
        "label", "products", "label IN ('adp', 'vehicle-world', 'milmod')", schema="catalog"
    )


def downgrade() -> None:
    op.drop_constraint("label", "products", schema="catalog", type_="check")
    op.drop_column("products", "label", schema="catalog")
