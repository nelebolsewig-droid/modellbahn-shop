"""Media (assets, image details, renditions) and catalogue (products, gauges, variants).

Written by hand like 0001. Constraint names follow the naming convention of
``modellbahn.platform.db``. The reference data of the catalogue (gauges, finishes,
epochs) is part of this migration: the code relies on its codes.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Periods are written with the typographic en dash (U+2013), as in German print.
DASH = "\u2013"
SEARCH_VECTOR = (
    "setweight(to_tsvector('german'::regconfig, name), 'A') || "
    "setweight(to_tsvector('german'::regconfig, summary), 'B') || "
    "setweight(to_tsvector('german'::regconfig, description), 'C')"
)


def upgrade() -> None:
    op.execute("CREATE SCHEMA media")
    op.execute("CREATE SCHEMA catalog")
    _create_media()
    _create_catalog()
    _seed_reference_data()


def _create_media() -> None:
    op.create_table(
        "assets",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        # Private storage key of the original: incoming/{id}/original.
        sa.Column("original_key", sa.Text(), nullable=False),
        sa.Column("original_filename", sa.Text(), nullable=False),
        sa.Column("mime_type", sa.Text(), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.CHAR(64), nullable=False),
        sa.Column("attempts", sa.SmallInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column("failure_code", sa.Text(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("uploaded_by", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ready_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_assets"),
        sa.UniqueConstraint("original_key", name="uq_assets_original_key"),
        sa.UniqueConstraint("kind", "sha256", name="uq_assets_kind_sha256"),
        # Target of the (id, kind) foreign keys that only accept assets of one kind.
        sa.UniqueConstraint("id", "kind", name="uq_assets_id_kind"),
        sa.CheckConstraint("kind IN ('image', 'model_3d')", name="ck_assets_kind"),
        sa.CheckConstraint(
            "status IN ('pending_upload', 'uploaded', 'ready', 'failed')", name="ck_assets_status"
        ),
        sa.CheckConstraint(
            "failure_code IN ('unsupported_format', 'too_many_pixels', 'too_small', "
            "'unreadable', 'processing_error')",
            name="ck_assets_failure_code",
        ),
        sa.CheckConstraint(
            "status <> 'failed' OR failure_code IS NOT NULL", name="ck_assets_failed_has_reason"
        ),
        sa.CheckConstraint(
            "char_length(original_filename) BETWEEN 1 AND 255", name="ck_assets_filename_length"
        ),
        sa.CheckConstraint("size_bytes > 0", name="ck_assets_size_positive"),
        sa.CheckConstraint("sha256 ~ '^[0-9a-f]{64}$'", name="ck_assets_sha256_format"),
        sa.CheckConstraint("attempts >= 0", name="ck_assets_attempts_non_negative"),
        # Across modules: never cascading. Accounts are anonymised rather than deleted.
        sa.ForeignKeyConstraint(
            ["uploaded_by"],
            ["identity.accounts.id"],
            name="fk_assets_uploaded_by_accounts",
            ondelete="SET NULL",
        ),
        schema="media",
    )
    op.create_index(
        "assets_pending_upload_idx",
        "assets",
        ["created_at"],
        schema="media",
        postgresql_where=sa.text("status = 'pending_upload'"),
    )

    op.create_table(
        "image_details",
        sa.Column("asset_id", sa.Uuid(), nullable=False),
        sa.Column("asset_kind", sa.Text(), server_default=sa.text("'image'"), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("dominant_color", sa.CHAR(7), nullable=False),
        sa.Column("lqip", sa.Text(), nullable=False),
        sa.Column("phash", sa.BigInteger(), nullable=False),
        sa.PrimaryKeyConstraint("asset_id", name="pk_image_details"),
        sa.CheckConstraint("asset_kind = 'image'", name="ck_image_details_asset_kind"),
        sa.CheckConstraint("width > 0 AND height > 0", name="ck_image_details_dimensions_positive"),
        sa.CheckConstraint(
            "dominant_color ~ '^#[0-9a-f]{6}$'", name="ck_image_details_dominant_color_format"
        ),
        sa.CheckConstraint("char_length(lqip) <= 4096", name="ck_image_details_lqip_length"),
        sa.ForeignKeyConstraint(
            ["asset_id", "asset_kind"],
            ["media.assets.id", "media.assets.kind"],
            name="fk_image_details_asset_id_asset_kind_assets",
            ondelete="CASCADE",
        ),
        schema="media",
    )

    op.create_table(
        "renditions",
        sa.Column("asset_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("format", sa.Text(), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        # Public storage key, content-addressed: {asset}/{name}-{hash8}.{format}.
        sa.Column("storage_key", sa.Text(), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("asset_id", "name", "format", name="pk_renditions"),
        sa.UniqueConstraint("storage_key", name="uq_renditions_storage_key"),
        sa.CheckConstraint(
            "name IN ('thumb', 'sm', 'md', 'lg', 'xl', 'og')", name="ck_renditions_name"
        ),
        sa.CheckConstraint("format IN ('webp', 'avif')", name="ck_renditions_format"),
        sa.CheckConstraint("width > 0 AND height > 0", name="ck_renditions_dimensions_positive"),
        sa.CheckConstraint("size_bytes > 0", name="ck_renditions_size_positive"),
        sa.ForeignKeyConstraint(
            ["asset_id"],
            ["media.assets.id"],
            name="fk_renditions_asset_id_assets",
            ondelete="CASCADE",
        ),
        schema="media",
    )


def _create_catalog() -> None:
    op.execute("CREATE SEQUENCE catalog.product_number_seq")
    op.execute("CREATE SEQUENCE catalog.gtin_serial_seq")

    op.create_table(
        "scales",
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("ratio_denominator", sa.SmallInteger(), nullable=False),
        sa.Column("track_gauge_mm", sa.Numeric(4, 1), nullable=False),
        sa.Column("position", sa.SmallInteger(), nullable=False),
        sa.PrimaryKeyConstraint("code", name="pk_scales"),
        sa.CheckConstraint("ratio_denominator > 0", name="ck_scales_ratio_positive"),
        schema="catalog",
    )
    op.create_table(
        "finishes",
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("sku_letter", sa.CHAR(1), nullable=False),
        sa.Column("position", sa.SmallInteger(), nullable=False),
        sa.PrimaryKeyConstraint("code", name="pk_finishes"),
        sa.UniqueConstraint("sku_letter", name="uq_finishes_sku_letter"),
        sa.CheckConstraint("sku_letter ~ '^[A-Z]$'", name="ck_finishes_sku_letter_format"),
        schema="catalog",
    )
    op.create_table(
        "epochs",
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("period", sa.Text(), nullable=False),
        sa.Column("position", sa.SmallInteger(), nullable=False),
        sa.PrimaryKeyConstraint("code", name="pk_epochs"),
        schema="catalog",
    )

    op.create_table(
        "categories",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("parent_id", sa.Uuid(), nullable=True),
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("position", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_categories"),
        sa.UniqueConstraint("slug", name="uq_categories_slug"),
        sa.CheckConstraint("char_length(name) BETWEEN 1 AND 60", name="ck_categories_name_length"),
        sa.CheckConstraint("parent_id <> id", name="ck_categories_not_own_parent"),
        sa.ForeignKeyConstraint(
            ["parent_id"],
            ["catalog.categories.id"],
            name="fk_categories_parent_id_categories",
            ondelete="RESTRICT",
        ),
        schema="catalog",
    )
    op.create_index("categories_parent_idx", "categories", ["parent_id"], schema="catalog")

    op.create_table(
        "products",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column("description", sa.Text(), server_default=sa.text("''"), nullable=False),
        # The prototype in real life, e.g. "Stellwerk Altenau (Harz), Deutsche Reichsbahn".
        sa.Column("prototype", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column("primary_category_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "search_vector",
            postgresql.TSVECTOR(),
            sa.Computed(SEARCH_VECTOR, persisted=True),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_products"),
        sa.UniqueConstraint("number", name="uq_products_number"),
        sa.UniqueConstraint("slug", name="uq_products_slug"),
        sa.CheckConstraint("status IN ('draft', 'active', 'archived')", name="ck_products_status"),
        sa.CheckConstraint("char_length(name) BETWEEN 1 AND 120", name="ck_products_name_length"),
        sa.CheckConstraint("slug ~ '^[a-z0-9]+(-[a-z0-9]+)*$'", name="ck_products_slug_format"),
        sa.CheckConstraint(
            "status <> 'active' OR (primary_category_id IS NOT NULL AND published_at IS NOT NULL)",
            name="ck_products_active_complete",
        ),
        sa.CheckConstraint(
            "(status = 'archived') = (archived_at IS NOT NULL)", name="ck_products_archived_at"
        ),
        sa.ForeignKeyConstraint(
            ["primary_category_id"],
            ["catalog.categories.id"],
            name="fk_products_primary_category_id_categories",
            ondelete="RESTRICT",
        ),
        schema="catalog",
    )
    op.create_index(
        "products_search_idx",
        "products",
        ["search_vector"],
        schema="catalog",
        postgresql_using="gin",
    )
    op.create_index(
        "products_active_idx",
        "products",
        ["published_at", "id"],
        schema="catalog",
        postgresql_where=sa.text("status = 'active'"),
    )
    op.create_index("products_category_idx", "products", ["primary_category_id"], schema="catalog")

    op.create_table(
        "product_epochs",
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("epoch_code", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("product_id", "epoch_code", name="pk_product_epochs"),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["catalog.products.id"],
            name="fk_product_epochs_product_id_products",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["epoch_code"],
            ["catalog.epochs.code"],
            name="fk_product_epochs_epoch_code_epochs",
            ondelete="RESTRICT",
        ),
        schema="catalog",
    )

    op.create_table(
        "product_scales",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("scale_code", sa.Text(), nullable=False),
        sa.Column("length_mm", sa.Numeric(6, 1), nullable=True),
        sa.Column("width_mm", sa.Numeric(6, 1), nullable=True),
        sa.Column("height_mm", sa.Numeric(6, 1), nullable=True),
        sa.Column("weight_g", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_product_scales"),
        sa.UniqueConstraint(
            "product_id", "scale_code", name="uq_product_scales_product_id_scale_code"
        ),
        sa.CheckConstraint(
            "(length_mm IS NULL OR length_mm > 0) AND (width_mm IS NULL OR width_mm > 0) "
            "AND (height_mm IS NULL OR height_mm > 0)",
            name="ck_product_scales_dimensions_positive",
        ),
        sa.CheckConstraint(
            "weight_g IS NULL OR weight_g > 0", name="ck_product_scales_weight_positive"
        ),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["catalog.products.id"],
            name="fk_product_scales_product_id_products",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["scale_code"],
            ["catalog.scales.code"],
            name="fk_product_scales_scale_code_scales",
            ondelete="RESTRICT",
        ),
        schema="catalog",
    )

    op.create_table(
        "variants",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("product_scale_id", sa.Uuid(), nullable=False),
        sa.Column("finish_code", sa.Text(), nullable=False),
        # MB-{product number}-{gauge}-{finish letter}, e.g. MB-000042-H0-B.
        sa.Column("sku", sa.Text(), nullable=False),
        # Internal EAN-13: prefix 20, serial from gtin_serial_seq, check digit.
        sa.Column("gtin", sa.CHAR(13), nullable=False),
        sa.Column("price_cents", sa.Integer(), nullable=False),
        sa.Column("compare_at_price_cents", sa.Integer(), nullable=True),
        sa.Column("allow_backorder", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_variants"),
        sa.UniqueConstraint("sku", name="uq_variants_sku"),
        sa.UniqueConstraint("gtin", name="uq_variants_gtin"),
        sa.UniqueConstraint(
            "product_scale_id", "finish_code", name="uq_variants_product_scale_id_finish_code"
        ),
        sa.CheckConstraint("price_cents >= 0", name="ck_variants_price_non_negative"),
        sa.CheckConstraint(
            "compare_at_price_cents IS NULL OR compare_at_price_cents > price_cents",
            name="ck_variants_compare_at_above_price",
        ),
        sa.CheckConstraint("gtin ~ '^2[0-9]{12}$'", name="ck_variants_gtin_format"),
        sa.ForeignKeyConstraint(
            ["product_scale_id"],
            ["catalog.product_scales.id"],
            name="fk_variants_product_scale_id_product_scales",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["finish_code"],
            ["catalog.finishes.code"],
            name="fk_variants_finish_code_finishes",
            ondelete="RESTRICT",
        ),
        schema="catalog",
    )
    op.create_index(
        "variants_product_scale_idx", "variants", ["product_scale_id"], schema="catalog"
    )

    op.create_table(
        "product_media",
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("asset_id", sa.Uuid(), nullable=False),
        sa.Column("asset_kind", sa.Text(), server_default=sa.text("'image'"), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("alt_text", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column("scale_code", sa.Text(), nullable=True),
        sa.Column("finish_code", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("product_id", "asset_id", name="pk_product_media"),
        # Checked at commit, so reordering the gallery is a single step.
        sa.UniqueConstraint(
            "product_id",
            "position",
            name="uq_product_media_product_id_position",
            deferrable=True,
            initially="DEFERRED",
        ),
        sa.CheckConstraint("asset_kind = 'image'", name="ck_product_media_asset_kind"),
        sa.CheckConstraint("position >= 0", name="ck_product_media_position_non_negative"),
        sa.CheckConstraint(
            "role IN ('gallery', 'detail', 'scale_comparison')", name="ck_product_media_role"
        ),
        sa.CheckConstraint("char_length(alt_text) <= 250", name="ck_product_media_alt_text_length"),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["catalog.products.id"],
            name="fk_product_media_product_id_products",
            ondelete="CASCADE",
        ),
        # Into the media module: only images, and an image in a gallery cannot be deleted.
        sa.ForeignKeyConstraint(
            ["asset_id", "asset_kind"],
            ["media.assets.id", "media.assets.kind"],
            name="fk_product_media_asset_id_asset_kind_assets",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["scale_code"],
            ["catalog.scales.code"],
            name="fk_product_media_scale_code_scales",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["finish_code"],
            ["catalog.finishes.code"],
            name="fk_product_media_finish_code_finishes",
            ondelete="RESTRICT",
        ),
        schema="catalog",
    )
    op.create_index("product_media_asset_idx", "product_media", ["asset_id"], schema="catalog")


def _seed_reference_data() -> None:
    scales = sa.table(
        "scales",
        sa.column("code", sa.Text()),
        sa.column("name", sa.Text()),
        sa.column("ratio_denominator", sa.SmallInteger()),
        sa.column("track_gauge_mm", sa.Numeric(4, 1)),
        sa.column("position", sa.SmallInteger()),
        schema="catalog",
    )
    op.bulk_insert(
        scales,
        [
            {
                "code": "H0",
                "name": "H0",
                "ratio_denominator": 87,
                "track_gauge_mm": 16.5,
                "position": 1,
            },
            {
                "code": "TT",
                "name": "TT",
                "ratio_denominator": 120,
                "track_gauge_mm": 12.0,
                "position": 2,
            },
            {
                "code": "N",
                "name": "N",
                "ratio_denominator": 160,
                "track_gauge_mm": 9.0,
                "position": 3,
            },
        ],
    )
    finishes = sa.table(
        "finishes",
        sa.column("code", sa.Text()),
        sa.column("name", sa.Text()),
        sa.column("sku_letter", sa.CHAR(1)),
        sa.column("position", sa.SmallInteger()),
        schema="catalog",
    )
    op.bulk_insert(
        finishes,
        [
            {"code": "unpainted", "name": "unbemalt", "sku_letter": "U", "position": 1},
            {"code": "primed", "name": "grundiert", "sku_letter": "G", "position": 2},
            {"code": "painted", "name": "bemalt", "sku_letter": "B", "position": 3},
        ],
    )
    epochs = sa.table(
        "epochs",
        sa.column("code", sa.Text()),
        sa.column("name", sa.Text()),
        sa.column("period", sa.Text()),
        sa.column("position", sa.SmallInteger()),
        schema="catalog",
    )
    op.bulk_insert(
        epochs,
        [
            {"code": "I", "name": "Epoche I", "period": f"1835{DASH}1920", "position": 1},
            {"code": "II", "name": "Epoche II", "period": f"1920{DASH}1949", "position": 2},
            {"code": "III", "name": "Epoche III", "period": f"1949{DASH}1970", "position": 3},
            {"code": "IV", "name": "Epoche IV", "period": f"1970{DASH}1990", "position": 4},
            {"code": "V", "name": "Epoche V", "period": f"1990{DASH}2006", "position": 5},
            {"code": "VI", "name": "Epoche VI", "period": "seit 2006", "position": 6},
        ],
    )


def downgrade() -> None:
    op.drop_table("product_media", schema="catalog")
    op.drop_table("variants", schema="catalog")
    op.drop_table("product_scales", schema="catalog")
    op.drop_table("product_epochs", schema="catalog")
    op.drop_table("products", schema="catalog")
    op.drop_table("categories", schema="catalog")
    op.drop_table("epochs", schema="catalog")
    op.drop_table("finishes", schema="catalog")
    op.drop_table("scales", schema="catalog")
    op.execute("DROP SEQUENCE catalog.gtin_serial_seq")
    op.execute("DROP SEQUENCE catalog.product_number_seq")
    op.drop_table("renditions", schema="media")
    op.drop_table("image_details", schema="media")
    op.drop_table("assets", schema="media")
    op.execute("DROP SCHEMA catalog")
    op.execute("DROP SCHEMA media")
