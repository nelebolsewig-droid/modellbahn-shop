"""One code per model: scans book several pieces at once, and book them out too.

Written by hand like the migrations before; constraint names follow the naming
convention of ``modellbahn.platform.db``.

- ``inventory.scans.mode`` may be ``scrap``: free pieces of a model leave the stock with
  a reason (*Ausbuchen*), as when taking units out by hand.
- ``inventory.scans.quantity``: how many pieces the scanned model label stood for (1 to
  200); every scan before counted one. A repeated scan id must bring the same quantity.

The journal needs nothing new: a scan books one entry per unit as before, and undoing
pieces a scan made scraps them as recorded by mistake.

Revision ID: 0019
Revises: 0018
Create Date: 2026-11-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0019"
down_revision: str | None = "0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_MODES_BEFORE = "mode IN ('put_away', 'pick', 'lookup')"
_MODES_AFTER = "mode IN ('put_away', 'pick', 'lookup', 'scrap')"


def upgrade() -> None:
    op.drop_constraint("ck_scans_mode", "scans", schema="inventory", type_="check")
    op.create_check_constraint("ck_scans_mode", "scans", _MODES_AFTER, schema="inventory")
    op.add_column(
        "scans",
        sa.Column("quantity", sa.SmallInteger(), nullable=False, server_default=sa.text("1")),
        schema="inventory",
    )
    op.create_check_constraint(
        "ck_scans_quantity_range", "scans", "quantity BETWEEN 1 AND 200", schema="inventory"
    )


def downgrade() -> None:
    # The older model knows no scans that book out. They become put-away scans, the
    # other mode that books; their journal entries still say what happened (scrap).
    op.drop_constraint("ck_scans_quantity_range", "scans", schema="inventory", type_="check")
    op.drop_column("scans", "quantity", schema="inventory")
    op.execute("UPDATE inventory.scans SET mode = 'put_away' WHERE mode = 'scrap'")
    op.drop_constraint("ck_scans_mode", "scans", schema="inventory", type_="check")
    op.create_check_constraint("ck_scans_mode", "scans", _MODES_BEFORE, schema="inventory")
