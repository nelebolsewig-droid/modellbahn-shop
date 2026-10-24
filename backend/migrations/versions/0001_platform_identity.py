"""Platform outbox and identity: accounts, sessions, one-time tokens.

Written by hand. Constraint names follow the naming convention of
``modellbahn.platform.db``, so the SQLAlchemy tables match this schema exactly.

Revision ID: 0001
Revises:
Create Date: 2026-10-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TOKEN_HASH_FORMAT = "token_hash ~ '^[0-9a-f]{64}$'"  # noqa: S105


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS citext")
    op.execute("CREATE SCHEMA platform")
    op.execute("CREATE SCHEMA identity")

    op.create_table(
        "outbox",
        # id = event id, a UUIDv7, so the primary key orders events by time.
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("aggregate_type", sa.Text(), nullable=False),
        sa.Column("aggregate_id", sa.Uuid(), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.Text(), server_default=sa.text("'pending'"), nullable=False),
        sa.Column("attempts", sa.SmallInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "next_attempt_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_outbox"),
        sa.CheckConstraint("status IN ('pending', 'published', 'dead')", name="ck_outbox_status"),
        sa.CheckConstraint("attempts >= 0", name="ck_outbox_attempts_non_negative"),
        sa.CheckConstraint(
            "(status = 'published') = (published_at IS NOT NULL)", name="ck_outbox_published_at"
        ),
        schema="platform",
    )
    op.create_index(
        "outbox_pending_idx",
        "outbox",
        ["next_attempt_at"],
        schema="platform",
        postgresql_where=sa.text("status = 'pending'"),
    )
    # Replay to reconnecting SSE clients (in publication order) and the retention purge.
    op.create_index(
        "outbox_published_idx",
        "outbox",
        ["published_at", "id"],
        schema="platform",
        postgresql_where=sa.text("status = 'published'"),
    )
    # The events of one aggregate: erasing personal data, throttling repeated requests.
    op.create_index("outbox_aggregate_idx", "outbox", ["aggregate_id"], schema="platform")

    op.create_table(
        "accounts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("email", postgresql.CITEXT(), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("role", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), server_default=sa.text("'active'"), nullable=False),
        sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "failed_login_count", sa.SmallInteger(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_accounts"),
        sa.UniqueConstraint("kind", "email", name="uq_accounts_kind_email"),
        # Target of the (id, kind) foreign keys that keep sessions in their own area.
        sa.UniqueConstraint("id", "kind", name="uq_accounts_id_kind"),
        sa.CheckConstraint("kind IN ('staff', 'customer')", name="ck_accounts_kind"),
        sa.CheckConstraint(
            "char_length(display_name) BETWEEN 1 AND 80", name="ck_accounts_display_name_length"
        ),
        sa.CheckConstraint("role IN ('owner', 'staff', 'packer')", name="ck_accounts_role"),
        sa.CheckConstraint("status IN ('active', 'deleted')", name="ck_accounts_status"),
        sa.CheckConstraint(
            "failed_login_count >= 0", name="ck_accounts_failed_login_count_non_negative"
        ),
        sa.CheckConstraint(
            "(kind = 'staff') = (role IS NOT NULL)", name="ck_accounts_role_only_for_staff"
        ),
        schema="identity",
    )

    op.create_table(
        "sessions",
        sa.Column("token_hash", sa.CHAR(64), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        # The area of the session; must equal the kind of the account (foreign key).
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("token_hash", name="pk_sessions"),
        sa.CheckConstraint(TOKEN_HASH_FORMAT, name="ck_sessions_token_hash_format"),
        sa.CheckConstraint("expires_at > created_at", name="ck_sessions_expires_after_creation"),
        sa.ForeignKeyConstraint(
            ["account_id", "kind"],
            ["identity.accounts.id", "identity.accounts.kind"],
            name="fk_sessions_account_id_kind_accounts",
            ondelete="CASCADE",
        ),
        schema="identity",
    )
    op.create_index("sessions_account_idx", "sessions", ["account_id"], schema="identity")

    op.create_table(
        "account_tokens",
        sa.Column("token_hash", sa.CHAR(64), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("purpose", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        # The outbox event that caused the token; makes the mail handlers idempotent.
        sa.Column("source_event_id", sa.Uuid(), nullable=True),
        sa.PrimaryKeyConstraint("token_hash", name="pk_account_tokens"),
        sa.UniqueConstraint("source_event_id", name="uq_account_tokens_source_event_id"),
        sa.CheckConstraint(TOKEN_HASH_FORMAT, name="ck_account_tokens_token_hash_format"),
        sa.CheckConstraint(
            "purpose IN ('verify_email', 'reset_password')", name="ck_account_tokens_purpose"
        ),
        sa.CheckConstraint(
            "expires_at > created_at", name="ck_account_tokens_expires_after_creation"
        ),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["identity.accounts.id"],
            name="fk_account_tokens_account_id_accounts",
            ondelete="CASCADE",
        ),
        schema="identity",
    )
    op.create_index(
        "account_tokens_account_idx",
        "account_tokens",
        ["account_id", "purpose"],
        schema="identity",
    )


def downgrade() -> None:
    op.drop_table("account_tokens", schema="identity")
    op.drop_table("sessions", schema="identity")
    op.drop_table("accounts", schema="identity")
    op.drop_table("outbox", schema="platform")
    op.execute("DROP SCHEMA identity")
    op.execute("DROP SCHEMA platform")
    # The citext extension stays: it belongs to the database, and other schemas
    # (or a later upgrade) may use it. CREATE EXTENSION IF NOT EXISTS copes with that.
