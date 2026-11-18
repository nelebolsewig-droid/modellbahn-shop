"""The photo studio: which photos it may finish, and which it did (ADR 0031).

Written by hand like the migrations before.

``media.assets.studio``: may the worker cut the model out and put it on the stage?
True for every new upload. The photos that are in the shop already keep their look:
they get ``false`` and can be switched on one by one in the gallery.

``media.image_details.studio_applied``: do the rendered sizes show the studio's
version? False when the studio is off or found no model in the photo.

Revision ID: 0022
Revises: 0021
Create Date: 2026-11-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0022"
down_revision: str | None = "0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "assets",
        sa.Column("studio", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        schema="media",
    )
    op.alter_column("assets", "studio", server_default=sa.text("true"), schema="media")
    op.add_column(
        "image_details",
        sa.Column("studio_applied", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        schema="media",
    )


def downgrade() -> None:
    op.drop_column("image_details", "studio_applied", schema="media")
    op.drop_column("assets", "studio", schema="media")
