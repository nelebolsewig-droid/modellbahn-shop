"""What a material costs: the price of a litre of resin or a kilogram of filament (ADR 0035).

Written by hand like the migrations before.

``manufacturing.materials.price_cents``: gross cents per litre (resin) or kilogram
(filament); empty while nobody entered it. With the amount each part takes and the bill
of materials it gives what a kit costs to print, which the store shows as Herstellwert.

Revision ID: 0024
Revises: 0023
Create Date: 2026-11-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0024"
down_revision: str | None = "0023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("materials", sa.Column("price_cents", sa.Integer()), schema="manufacturing")
    op.create_check_constraint(
        "ck_materials_price_cents",
        "materials",
        "price_cents IS NULL OR price_cents > 0",
        schema="manufacturing",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_materials_price_cents", "materials", schema="manufacturing", type_="check"
    )
    op.drop_column("materials", "price_cents", schema="manufacturing")
