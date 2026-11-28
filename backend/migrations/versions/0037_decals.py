"""Decals beside the models: a finish "Decal" and a top-level category "Decals".

Decals are created like models (scale, price, photos) but sold as a decal sheet, neither
kit nor finished model. The shop shows the "decals" branch under its own heading.
Written by hand like the migrations before.

Revision ID: 0037
Revises: 0036
Create Date: 2026-11-28
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0037"
down_revision: str | None = "0036"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "INSERT INTO catalog.finishes (code, name, sku_letter, position, colored, offered) "
        "VALUES ('decal', 'Decal', 'D', 4, false, true) ON CONFLICT (code) DO NOTHING"
    )
    op.execute(
        "INSERT INTO catalog.categories "
        "(id, parent_id, slug, name, position, created_at, updated_at) "
        "SELECT gen_random_uuid(), NULL, 'decals', 'Decals', "
        "COALESCE((SELECT max(position) + 1 FROM catalog.categories WHERE parent_id IS NULL), 0), "
        "now(), now() "
        "WHERE NOT EXISTS (SELECT 1 FROM catalog.categories WHERE slug = 'decals')"
    )


def downgrade() -> None:
    op.execute(
        "DELETE FROM catalog.categories c WHERE c.slug = 'decals' "
        "AND NOT EXISTS (SELECT 1 FROM catalog.categories s WHERE s.parent_id = c.id) "
        "AND NOT EXISTS (SELECT 1 FROM catalog.products p WHERE p.primary_category_id = c.id)"
    )
    op.execute(
        "DELETE FROM catalog.finishes f WHERE f.code = 'decal' "
        "AND NOT EXISTS (SELECT 1 FROM catalog.variants v WHERE v.finish_code = 'decal')"
    )
