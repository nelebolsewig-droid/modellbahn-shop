"""Catalogue: kit and finished model, colours, primed no longer offered (ADR 0013).

- The finishes become "Bausatz" (``unpainted``, letter B) and "Fertigmodell"
  (``painted``, letter F, in colours); the article numbers follow the new letters.
- "grundiert" (``primed``) is no longer offered. Its variants without stock go; those
  with stock stay, switched off, for the history of their pieces.
- A variant has a colour (empty for a kit), unique per scale and finish; a gallery
  image may say which colour it shows.

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "finishes",
        sa.Column("colored", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        schema="catalog",
    )
    op.add_column(
        "finishes",
        sa.Column("offered", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        schema="catalog",
    )
    # The letters are unique: painted gives up B before the kit takes it.
    op.execute(
        "UPDATE catalog.finishes SET name = 'Fertigmodell', sku_letter = 'F', colored = true, "
        "position = 2 WHERE code = 'painted'"
    )
    op.execute(
        "UPDATE catalog.finishes SET name = 'Bausatz', sku_letter = 'B', position = 1 "
        "WHERE code = 'unpainted'"
    )
    op.execute("UPDATE catalog.finishes SET offered = false, position = 3 WHERE code = 'primed'")
    op.execute(
        "UPDATE catalog.variants SET sku = regexp_replace(sku, '-B$', '-F') "
        "WHERE finish_code = 'painted'"
    )
    op.execute(
        "UPDATE catalog.variants SET sku = regexp_replace(sku, '-U$', '-B') "
        "WHERE finish_code = 'unpainted'"
    )

    # Primed variants: without pieces in stock they go, with pieces they are switched off.
    op.execute(
        "DELETE FROM catalog.variants v WHERE v.finish_code = 'primed' "
        "AND NOT EXISTS (SELECT 1 FROM inventory.units u WHERE u.variant_id = v.id)"
    )
    op.execute("UPDATE catalog.variants SET active = false WHERE finish_code = 'primed'")
    op.execute("UPDATE catalog.product_media SET finish_code = NULL WHERE finish_code = 'primed'")

    op.add_column(
        "variants",
        sa.Column("color", sa.Text(), server_default=sa.text("''"), nullable=False),
        schema="catalog",
    )
    op.drop_constraint(
        "uq_variants_product_scale_id_finish_code", "variants", schema="catalog", type_="unique"
    )
    op.create_unique_constraint(
        "uq_variants_product_scale_id_finish_code_color",
        "variants",
        ["product_scale_id", "finish_code", "color"],
        schema="catalog",
    )
    op.create_check_constraint(
        "ck_variants_color_length", "variants", "char_length(color) <= 40", schema="catalog"
    )
    op.create_check_constraint(
        "ck_variants_kit_without_color",
        "variants",
        "finish_code <> 'unpainted' OR color = ''",
        schema="catalog",
    )
    op.add_column("product_media", sa.Column("color", sa.Text(), nullable=True), schema="catalog")
    op.create_check_constraint(
        "ck_product_media_color_length",
        "product_media",
        "color IS NULL OR char_length(color) BETWEEN 1 AND 40",
        schema="catalog",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_product_media_color_length", "product_media", schema="catalog", type_="check"
    )
    op.drop_column("product_media", "color", schema="catalog")
    # Several colours of one finish cannot go back to "one variant per finish".
    op.execute(
        "DO $$ BEGIN IF EXISTS (SELECT 1 FROM catalog.variants WHERE color <> '') THEN "
        "RAISE EXCEPTION 'variants with colours exist; remove them before downgrading'; "
        "END IF; END $$"
    )
    op.drop_constraint("ck_variants_kit_without_color", "variants", schema="catalog", type_="check")
    op.drop_constraint("ck_variants_color_length", "variants", schema="catalog", type_="check")
    op.drop_constraint(
        "uq_variants_product_scale_id_finish_code_color",
        "variants",
        schema="catalog",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_variants_product_scale_id_finish_code",
        "variants",
        ["product_scale_id", "finish_code"],
        schema="catalog",
    )
    op.drop_column("variants", "color", schema="catalog")
    op.execute(
        "UPDATE catalog.variants SET sku = regexp_replace(sku, '-B$', '-U') "
        "WHERE finish_code = 'unpainted'"
    )
    op.execute(
        "UPDATE catalog.variants SET sku = regexp_replace(sku, '-F$', '-B') "
        "WHERE finish_code = 'painted'"
    )
    op.execute(
        "UPDATE catalog.finishes SET name = 'unbemalt', sku_letter = 'U', position = 1 "
        "WHERE code = 'unpainted'"
    )
    op.execute(
        "UPDATE catalog.finishes SET name = 'bemalt', sku_letter = 'B', position = 3 "
        "WHERE code = 'painted'"
    )
    op.execute("UPDATE catalog.finishes SET position = 2 WHERE code = 'primed'")
    op.drop_column("finishes", "offered", schema="catalog")
    op.drop_column("finishes", "colored", schema="catalog")
