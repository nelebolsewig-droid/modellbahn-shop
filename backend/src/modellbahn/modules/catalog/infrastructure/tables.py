"""SQLAlchemy Core tables of the ``catalog`` schema.

They mirror migration ``0002_media_catalog`` exactly, including constraint names;
``tests/integration/test_migrations.py`` compares both.
"""

from sqlalchemy import (
    CHAR,
    Boolean,
    CheckConstraint,
    Column,
    Computed,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    PrimaryKeyConstraint,
    Sequence,
    SmallInteger,
    Table,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import TSVECTOR

from modellbahn.modules.catalog.domain.model import MediaRole, ProductStatus
from modellbahn.modules.media.contracts.images import IMAGE_KIND, IMAGE_REFERENCE
from modellbahn.platform.db import StrEnumType, metadata

SCHEMA = "catalog"

# Readable product numbers (MB-000042) and the serial part of the internal EANs.
product_number_seq = Sequence("product_number_seq", schema=SCHEMA, metadata=metadata)
gtin_serial_seq = Sequence("gtin_serial_seq", schema=SCHEMA, metadata=metadata)

# German full-text search: name weighs most, then summary, then description.
SEARCH_VECTOR_EXPRESSION = (
    "setweight(to_tsvector('german'::regconfig, name), 'A') || "
    "setweight(to_tsvector('german'::regconfig, summary), 'B') || "
    "setweight(to_tsvector('german'::regconfig, description), 'C')"
)

scales = Table(
    "scales",
    metadata,
    Column("code", Text, primary_key=True),
    Column("name", Text, nullable=False, unique=True),
    Column("ratio_denominator", Numeric(5, 1), nullable=False),
    # Road vehicles have a scale but no track.
    Column("track_gauge_mm", Numeric(4, 1)),
    CheckConstraint("ratio_denominator > 1 AND ratio_denominator <= 1000", name="ratio_range"),
    CheckConstraint("track_gauge_mm IS NULL OR track_gauge_mm > 0", name="track_gauge_positive"),
    CheckConstraint("code ~ '^[A-Z0-9]{1,4}$'", name="code_format"),
    schema=SCHEMA,
)

finishes = Table(
    "finishes",
    metadata,
    Column("code", Text, primary_key=True),
    Column("name", Text, nullable=False),
    Column("sku_letter", CHAR(1), nullable=False, unique=True),
    Column("position", SmallInteger, nullable=False),
    CheckConstraint("sku_letter ~ '^[A-Z]$'", name="sku_letter_format"),
    schema=SCHEMA,
)

epochs = Table(
    "epochs",
    metadata,
    Column("code", Text, primary_key=True),
    Column("name", Text, nullable=False),
    Column("period", Text, nullable=False),
    Column("position", SmallInteger, nullable=False),
    schema=SCHEMA,
)

categories = Table(
    "categories",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("parent_id", Uuid, ForeignKey("catalog.categories.id", ondelete="RESTRICT")),
    Column("slug", Text, nullable=False, unique=True),
    Column("name", Text, nullable=False),
    Column("position", Integer, nullable=False, server_default=text("0")),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    CheckConstraint("char_length(name) BETWEEN 1 AND 60", name="name_length"),
    CheckConstraint("parent_id <> id", name="not_own_parent"),
    Index("categories_parent_idx", "parent_id"),
    schema=SCHEMA,
)

products = Table(
    "products",
    metadata,
    Column("id", Uuid, primary_key=True),
    # Drawn from product_number_seq by the repository before the product is created.
    Column("number", Integer, nullable=False, unique=True),
    Column("slug", Text, nullable=False, unique=True),
    Column("name", Text, nullable=False),
    Column("summary", Text, nullable=False, server_default=text("''")),
    Column("description", Text, nullable=False, server_default=text("''")),
    Column("prototype", Text, nullable=False, server_default=text("''")),
    Column("primary_category_id", Uuid, ForeignKey(categories.c.id, ondelete="RESTRICT")),
    Column("status", StrEnumType(ProductStatus), nullable=False),
    Column("published_at", DateTime(timezone=True)),
    Column("archived_at", DateTime(timezone=True)),
    Column("search_vector", TSVECTOR, Computed(SEARCH_VECTOR_EXPRESSION, persisted=True)),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Column("version", Integer, nullable=False, server_default=text("1")),
    CheckConstraint("status IN ('draft', 'active', 'archived')", name="status"),
    CheckConstraint("char_length(name) BETWEEN 1 AND 120", name="name_length"),
    CheckConstraint("slug ~ '^[a-z0-9]+(-[a-z0-9]+)*$'", name="slug_format"),
    # A product in the shop has a category; one that was published keeps its date.
    CheckConstraint(
        "status <> 'active' OR (primary_category_id IS NOT NULL AND published_at IS NOT NULL)",
        name="active_complete",
    ),
    CheckConstraint("(status = 'archived') = (archived_at IS NOT NULL)", name="archived_at"),
    Index("products_search_idx", "search_vector", postgresql_using="gin"),
    # The shop lists active products, newest first.
    Index(
        "products_active_idx",
        "published_at",
        "id",
        postgresql_where=text("status = 'active'"),
    ),
    Index("products_category_idx", "primary_category_id"),
    schema=SCHEMA,
)

product_epochs = Table(
    "product_epochs",
    metadata,
    Column("product_id", Uuid, ForeignKey(products.c.id, ondelete="CASCADE"), nullable=False),
    Column("epoch_code", Text, ForeignKey(epochs.c.code, ondelete="RESTRICT"), nullable=False),
    PrimaryKeyConstraint("product_id", "epoch_code"),
    schema=SCHEMA,
)

product_scales = Table(
    "product_scales",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("product_id", Uuid, ForeignKey(products.c.id, ondelete="CASCADE"), nullable=False),
    Column("scale_code", Text, ForeignKey(scales.c.code, ondelete="RESTRICT"), nullable=False),
    Column("length_mm", Numeric(6, 1)),
    Column("width_mm", Numeric(6, 1)),
    Column("height_mm", Numeric(6, 1)),
    Column("weight_g", Integer),
    # One row per scale and product.
    UniqueConstraint("product_id", "scale_code"),
    CheckConstraint(
        "(length_mm IS NULL OR length_mm > 0) AND (width_mm IS NULL OR width_mm > 0) "
        "AND (height_mm IS NULL OR height_mm > 0)",
        name="dimensions_positive",
    ),
    CheckConstraint("weight_g IS NULL OR weight_g > 0", name="weight_positive"),
    schema=SCHEMA,
)

variants = Table(
    "variants",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column(
        "product_scale_id",
        Uuid,
        ForeignKey(product_scales.c.id, ondelete="CASCADE"),
        nullable=False,
    ),
    Column("finish_code", Text, ForeignKey(finishes.c.code, ondelete="RESTRICT"), nullable=False),
    Column("sku", Text, nullable=False, unique=True),
    Column("gtin", CHAR(13), nullable=False, unique=True),
    Column("price_cents", Integer, nullable=False),
    Column("compare_at_price_cents", Integer),
    Column("allow_backorder", Boolean, nullable=False, server_default=text("false")),
    Column("lead_time_min_weeks", SmallInteger),
    Column("lead_time_max_weeks", SmallInteger),
    Column("active", Boolean, nullable=False, server_default=text("true")),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    # Each scale is sold at most once in each finish.
    UniqueConstraint("product_scale_id", "finish_code"),
    CheckConstraint("price_cents >= 0", name="price_non_negative"),
    CheckConstraint(
        "compare_at_price_cents IS NULL OR compare_at_price_cents > price_cents",
        name="compare_at_above_price",
    ),
    # Internal numbers (GS1 prefix 20) only, until the shop has its own GS1 prefix.
    CheckConstraint("gtin ~ '^2[0-9]{12}$'", name="gtin_format"),
    # Made to order means a lead time: a range of weeks within a year.
    CheckConstraint(
        "(lead_time_min_weeks IS NULL) = (lead_time_max_weeks IS NULL)", name="lead_time_pair"
    ),
    CheckConstraint(
        "lead_time_min_weeks IS NULL OR (lead_time_min_weeks BETWEEN 1 AND 52 "
        "AND lead_time_max_weeks BETWEEN lead_time_min_weeks AND 52)",
        name="lead_time_range",
    ),
    CheckConstraint(
        "NOT allow_backorder OR lead_time_min_weeks IS NOT NULL", name="made_to_order_lead_time"
    ),
    Index("variants_product_scale_idx", "product_scale_id"),
    schema=SCHEMA,
)

product_media = Table(
    "product_media",
    metadata,
    Column("product_id", Uuid, ForeignKey(products.c.id, ondelete="CASCADE"), nullable=False),
    Column("asset_id", Uuid, nullable=False),
    # Always 'image': with the foreign key below a gallery takes no other kind of asset.
    Column("asset_kind", Text, nullable=False, server_default=text(f"'{IMAGE_KIND}'")),
    Column("position", Integer, nullable=False),
    Column("role", StrEnumType(MediaRole), nullable=False),
    Column("alt_text", Text, nullable=False, server_default=text("''")),
    Column("scale_code", Text, ForeignKey(scales.c.code, ondelete="RESTRICT")),
    Column("finish_code", Text, ForeignKey(finishes.c.code, ondelete="RESTRICT")),
    PrimaryKeyConstraint("product_id", "asset_id"),
    # Checked at commit, so reordering the gallery is a single step.
    UniqueConstraint("product_id", "position", deferrable=True, initially="DEFERRED"),
    CheckConstraint(f"asset_kind = '{IMAGE_KIND}'", name="asset_kind"),
    CheckConstraint("position >= 0", name="position_non_negative"),
    CheckConstraint("role IN ('gallery', 'detail', 'scale_comparison')", name="role"),
    CheckConstraint("char_length(alt_text) <= 250", name="alt_text_length"),
    # Into another module: an image in a gallery cannot be deleted.
    ForeignKeyConstraint(["asset_id", "asset_kind"], list(IMAGE_REFERENCE), ondelete="RESTRICT"),
    Index("product_media_asset_idx", "asset_id"),
    schema=SCHEMA,
)
