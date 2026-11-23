"""Count photo studio runs, so a run killed for memory does not repeat for ever (ADR 0031).

Written by hand like the migrations before.

- ``media.assets.studio_tries``: studio runs begun for a photo without a result. The
  worker commits the count before the run; after two the photo is rendered as taken.

Revision ID: 0032
Revises: 0031
Create Date: 2026-11-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0032"
down_revision: str | None = "0031"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "assets",
        sa.Column("studio_tries", sa.SmallInteger(), nullable=False, server_default=sa.text("0")),
        schema="media",
    )
    op.create_check_constraint(
        "ck_assets_studio_tries_non_negative", "assets", "studio_tries >= 0", schema="media"
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_assets_studio_tries_non_negative", "assets", schema="media", type_="check"
    )
    op.drop_column("assets", "studio_tries", schema="media")
