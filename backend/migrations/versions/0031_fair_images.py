"""A photo per fair (ADR 0044).

Written by hand like the migrations before.

- ``site.fairs.image_asset_id``: the photo shown with the fair (the booth, say), an image
  of the media module. Deleting the image takes it off the fair.

Revision ID: 0031
Revises: 0030
Create Date: 2026-11-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0031"
down_revision: str | None = "0030"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("fairs", sa.Column("image_asset_id", sa.Uuid()), schema="site")
    op.create_foreign_key(
        "fk_fairs_image_asset_id_assets",
        "fairs",
        "assets",
        ["image_asset_id"],
        ["id"],
        source_schema="site",
        referent_schema="media",
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_fairs_image_asset_id_assets", "fairs", schema="site", type_="foreignkey")
    op.drop_column("fairs", "image_asset_id", schema="site")
