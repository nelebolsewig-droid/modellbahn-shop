"""Why a unit was taken out by hand (*Ausbuchen*), kept as a value, not only as a note.

Written by hand like the migrations before; constraint names follow the naming
convention of ``modellbahn.platform.db``.

- ``inventory.units.scrap_reason``: sold (fair, shop, privately), damaged, missing at
  stocktaking, recorded by mistake. Empty for units scrapped before; ``scrap_note`` stays
  the free text next to it.

Revision ID: 0017
Revises: 0016
Create Date: 2026-11-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0017"
down_revision: str | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("units", sa.Column("scrap_reason", sa.Text(), nullable=True), schema="inventory")
    op.create_check_constraint(
        "ck_units_scrap_reason",
        "units",
        "scrap_reason IN ('sold', 'damaged', 'missing', 'mistake')",
        schema="inventory",
    )
    op.create_check_constraint(
        "ck_units_scrap_reason_when_scrapped",
        "units",
        "scrap_reason IS NULL OR status = 'scrapped'",
        schema="inventory",
    )


def downgrade() -> None:
    op.drop_constraint("ck_units_scrap_reason_when_scrapped", "units", schema="inventory")
    op.drop_constraint("ck_units_scrap_reason", "units", schema="inventory")
    op.drop_column("units", "scrap_reason", schema="inventory")
