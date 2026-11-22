"""Visitors per day, counted without cookies (ADR 0043).

Written by hand like the migrations before.

- ``site.visit_days``: per day the visitors and page views, and the day's salt, which is
  dropped once the day is over.
- ``site.visit_marks``: the hashed visitors of the current day, deleted the day after.

Revision ID: 0030
Revises: 0029
Create Date: 2026-11-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0030"
down_revision: str | None = "0029"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "visit_days",
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("salt", sa.LargeBinary()),
        sa.Column("visitors", sa.Integer(), nullable=False),
        sa.Column("page_views", sa.Integer(), nullable=False),
        sa.CheckConstraint("visitors >= 0 AND page_views >= visitors", name="ck_visit_days_counts"),
        sa.PrimaryKeyConstraint("day", name="pk_visit_days"),
        schema="site",
    )
    op.create_table(
        "visit_marks",
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("mark", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("day", "mark", name="pk_visit_marks"),
        schema="site",
    )


def downgrade() -> None:
    op.drop_table("visit_marks", schema="site")
    op.drop_table("visit_days", schema="site")
