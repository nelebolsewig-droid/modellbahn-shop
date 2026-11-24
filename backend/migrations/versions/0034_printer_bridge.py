"""Print jobs remember what the printer bridge reported (ADR 0047).

Written by hand like the migrations before.

- ``manufacturing.print_jobs.slice_file``: the file the printer printed.
- ``manufacturing.print_jobs.printer_task_id``: the printer's own id of the print, unique,
  so a print reported again is never booked twice.

Revision ID: 0034
Revises: 0033
Create Date: 2026-11-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0034"
down_revision: str | None = "0033"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "print_jobs",
        sa.Column("slice_file", sa.Text(), nullable=False, server_default=sa.text("''")),
        schema="manufacturing",
    )
    op.add_column("print_jobs", sa.Column("printer_task_id", sa.Text()), schema="manufacturing")
    op.create_index(
        "print_jobs_printer_task_idx",
        "print_jobs",
        ["printer_task_id"],
        unique=True,
        schema="manufacturing",
        postgresql_where=sa.text("printer_task_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("print_jobs_printer_task_idx", table_name="print_jobs", schema="manufacturing")
    op.drop_column("print_jobs", "printer_task_id", schema="manufacturing")
    op.drop_column("print_jobs", "slice_file", schema="manufacturing")
