"""Two more journal reasons: booking a scrapped unit in again, and correcting its variant.

Written by hand like the migrations before; constraint names follow the naming
convention of ``modellbahn.platform.db``.

- ``inventory.stock_ledger.reason`` may be ``restore``: a scrapped unit goes back into a
  location (*Wieder einbuchen*).
- ``inventory.stock_ledger.reason`` may be ``correct``: the unit is another variant than
  its label said (*Ausführung ändern*). The entry's ``variant_id`` is the new variant; the
  unit's entry before it carries the old one, so the journal needs no new column.

Revision ID: 0018
Revises: 0017
Create Date: 2026-11-12
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0018"
down_revision: str | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_REASONS_BEFORE = (
    "reason IN ('label', 'put_away', 'move', 'allocate', 'release', 'pick', 'ship', "
    "'scrap', 'undo')"
)
_REASONS_AFTER = (
    "reason IN ('label', 'put_away', 'move', 'allocate', 'release', 'pick', 'ship', "
    "'scrap', 'undo', 'restore', 'correct')"
)


def upgrade() -> None:
    op.drop_constraint("ck_stock_ledger_reason", "stock_ledger", schema="inventory", type_="check")
    op.create_check_constraint(
        "ck_stock_ledger_reason", "stock_ledger", _REASONS_AFTER, schema="inventory"
    )


def downgrade() -> None:
    # The older model knows neither reason. Booking in again comes closest to putting a
    # unit away; a correction stays a movement in place (its variant id still tells).
    op.execute("UPDATE inventory.stock_ledger SET reason = 'put_away' WHERE reason = 'restore'")
    op.execute("UPDATE inventory.stock_ledger SET reason = 'move' WHERE reason = 'correct'")
    op.drop_constraint("ck_stock_ledger_reason", "stock_ledger", schema="inventory", type_="check")
    op.create_check_constraint(
        "ck_stock_ledger_reason", "stock_ledger", _REASONS_BEFORE, schema="inventory"
    )
