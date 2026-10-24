"""SQLAlchemy Core tables of the ``media`` schema.

They mirror migration ``0002_media_catalog`` exactly, including constraint names;
``tests/integration/test_migrations.py`` compares both.
"""

from sqlalchemy import (
    CHAR,
    BigInteger,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    PrimaryKeyConstraint,
    SmallInteger,
    Table,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)

from modellbahn.modules.identity.contracts.accounts import ACCOUNT_REFERENCE
from modellbahn.modules.media.domain.errors import FailureCode
from modellbahn.modules.media.domain.model import AssetKind, AssetStatus
from modellbahn.modules.media.domain.renditions import RenditionFormat
from modellbahn.platform.db import StrEnumType, metadata

SCHEMA = "media"

assets = Table(
    "assets",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("kind", StrEnumType(AssetKind), nullable=False),
    Column("status", StrEnumType(AssetStatus), nullable=False),
    Column("original_key", Text, nullable=False, unique=True),
    Column("original_filename", Text, nullable=False),
    Column("mime_type", Text, nullable=False),
    Column("size_bytes", BigInteger, nullable=False),
    Column("sha256", CHAR(64), nullable=False),
    Column("attempts", SmallInteger, nullable=False, server_default=text("0")),
    Column("failure_code", StrEnumType(FailureCode)),
    Column("last_error", Text),
    # Who uploaded it; kept when the staff account is anonymised.
    Column("uploaded_by", Uuid, ForeignKey(ACCOUNT_REFERENCE, ondelete="SET NULL")),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Column("ready_at", DateTime(timezone=True)),
    Column("version", Integer, nullable=False, server_default=text("1")),
    # The same file uploaded twice is the same asset.
    UniqueConstraint("kind", "sha256"),
    # Target of the (id, kind) foreign keys that only accept assets of one kind.
    UniqueConstraint("id", "kind"),
    CheckConstraint("kind IN ('image', 'model_3d')", name="kind"),
    CheckConstraint("status IN ('pending_upload', 'uploaded', 'ready', 'failed')", name="status"),
    CheckConstraint(
        "failure_code IN ('unsupported_format', 'too_many_pixels', 'too_small', 'unreadable', "
        "'processing_error')",
        name="failure_code",
    ),
    CheckConstraint("status <> 'failed' OR failure_code IS NOT NULL", name="failed_has_reason"),
    CheckConstraint("char_length(original_filename) BETWEEN 1 AND 255", name="filename_length"),
    CheckConstraint("size_bytes > 0", name="size_positive"),
    CheckConstraint("sha256 ~ '^[0-9a-f]{64}$'", name="sha256_format"),
    CheckConstraint("attempts >= 0", name="attempts_non_negative"),
    # Finds abandoned upload tickets for the hourly clean-up.
    Index(
        "assets_pending_upload_idx",
        "created_at",
        postgresql_where=text("status = 'pending_upload'"),
    ),
    schema=SCHEMA,
)

image_details = Table(
    "image_details",
    metadata,
    Column("asset_id", Uuid, primary_key=True),
    # Always 'image': with the foreign key below only images can have image details.
    Column("asset_kind", Text, nullable=False, server_default=text("'image'")),
    Column("width", Integer, nullable=False),
    Column("height", Integer, nullable=False),
    Column("dominant_color", CHAR(7), nullable=False),
    Column("lqip", Text, nullable=False),
    Column("phash", BigInteger, nullable=False),
    CheckConstraint("asset_kind = 'image'", name="asset_kind"),
    CheckConstraint("width > 0 AND height > 0", name="dimensions_positive"),
    CheckConstraint("dominant_color ~ '^#[0-9a-f]{6}$'", name="dominant_color_format"),
    CheckConstraint("char_length(lqip) <= 4096", name="lqip_length"),
    ForeignKeyConstraint(
        ["asset_id", "asset_kind"], [assets.c.id, assets.c.kind], ondelete="CASCADE"
    ),
    schema=SCHEMA,
)

renditions = Table(
    "renditions",
    metadata,
    Column("asset_id", Uuid, ForeignKey(assets.c.id, ondelete="CASCADE"), nullable=False),
    Column("name", Text, nullable=False),
    Column("format", StrEnumType(RenditionFormat), nullable=False),
    Column("width", Integer, nullable=False),
    Column("height", Integer, nullable=False),
    Column("storage_key", Text, nullable=False, unique=True),
    Column("size_bytes", Integer, nullable=False),
    PrimaryKeyConstraint("asset_id", "name", "format"),
    CheckConstraint("name IN ('thumb', 'sm', 'md', 'lg', 'xl', 'og')", name="name"),
    CheckConstraint("format IN ('webp', 'avif')", name="format"),
    CheckConstraint("width > 0 AND height > 0", name="dimensions_positive"),
    CheckConstraint("size_bytes > 0", name="size_positive"),
    schema=SCHEMA,
)
