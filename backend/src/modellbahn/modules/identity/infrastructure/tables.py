"""SQLAlchemy Core tables of the ``identity`` schema.

They mirror migration ``0001_platform_identity`` exactly, including constraint
names; ``tests/integration/test_migrations.py`` compares both.
"""

from sqlalchemy import (
    CHAR,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    SmallInteger,
    Table,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import CITEXT

from modellbahn.modules.identity.domain.model import (
    AccountKind,
    AccountStatus,
    StaffRole,
    TokenPurpose,
)
from modellbahn.platform.db import StrEnumType, metadata

SCHEMA = "identity"

accounts = Table(
    "accounts",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("kind", StrEnumType(AccountKind), nullable=False),
    Column("email", CITEXT, nullable=False),
    Column("display_name", Text, nullable=False),
    Column("password_hash", Text, nullable=False),
    Column("role", StrEnumType(StaffRole)),
    Column("status", StrEnumType(AccountStatus), nullable=False, server_default=text("'active'")),
    Column("email_verified_at", DateTime(timezone=True)),
    Column("failed_login_count", SmallInteger, nullable=False, server_default=text("0")),
    Column("locked_until", DateTime(timezone=True)),
    Column("last_login_at", DateTime(timezone=True)),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Column("version", Integer, nullable=False, server_default=text("1")),
    UniqueConstraint("kind", "email"),
    # Target of the (id, kind) foreign keys that keep sessions in their own area.
    UniqueConstraint("id", "kind"),
    CheckConstraint("kind IN ('staff', 'customer')", name="kind"),
    CheckConstraint("char_length(display_name) BETWEEN 1 AND 80", name="display_name_length"),
    CheckConstraint("role IN ('owner', 'staff', 'packer')", name="role"),
    CheckConstraint("status IN ('active', 'deleted')", name="status"),
    CheckConstraint("failed_login_count >= 0", name="failed_login_count_non_negative"),
    CheckConstraint("(kind = 'staff') = (role IS NOT NULL)", name="role_only_for_staff"),
    schema=SCHEMA,
)

sessions = Table(
    "sessions",
    metadata,
    Column("token_hash", CHAR(64), primary_key=True),
    Column("account_id", Uuid, nullable=False),
    Column("kind", StrEnumType(AccountKind), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("expires_at", DateTime(timezone=True), nullable=False),
    Column("last_seen_at", DateTime(timezone=True), nullable=False),
    Column("user_agent", Text),
    CheckConstraint("token_hash ~ '^[0-9a-f]{64}$'", name="token_hash_format"),
    CheckConstraint("expires_at > created_at", name="expires_after_creation"),
    ForeignKeyConstraint(
        ["account_id", "kind"],
        [accounts.c.id, accounts.c.kind],
        ondelete="CASCADE",
    ),
    Index("sessions_account_idx", "account_id"),
    schema=SCHEMA,
)

account_tokens = Table(
    "account_tokens",
    metadata,
    Column("token_hash", CHAR(64), primary_key=True),
    Column("account_id", Uuid, ForeignKey(accounts.c.id, ondelete="CASCADE"), nullable=False),
    Column("purpose", StrEnumType(TokenPurpose), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("expires_at", DateTime(timezone=True), nullable=False),
    Column("used_at", DateTime(timezone=True)),
    # The outbox event that caused the token; makes the mail handlers idempotent.
    Column("source_event_id", Uuid, unique=True),
    CheckConstraint("token_hash ~ '^[0-9a-f]{64}$'", name="token_hash_format"),
    CheckConstraint("purpose IN ('verify_email', 'reset_password')", name="purpose"),
    CheckConstraint("expires_at > created_at", name="expires_after_creation"),
    Index("account_tokens_account_idx", "account_id", "purpose"),
    schema=SCHEMA,
)
