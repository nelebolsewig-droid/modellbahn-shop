"""Site: the fairs the workshop exhibits at and the fair news by e-mail (double opt-in).

Written by hand like the migrations before; constraint names follow the naming
convention of ``modellbahn.platform.db``.

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA site")
    _create_fairs()
    _create_subscriptions()
    _create_mailings()


def _create_fairs() -> None:
    op.create_table(
        "fairs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("venue", sa.Text(), nullable=False),
        sa.Column("street", sa.Text(), nullable=False),
        sa.Column("postal_code", sa.Text(), nullable=False),
        sa.Column("city", sa.Text(), nullable=False),
        sa.Column("booth", sa.Text(), nullable=False),
        sa.Column("hours", sa.Text(), nullable=False),
        sa.Column("website_url", sa.Text(), nullable=False),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("starts_on", sa.Date(), nullable=False),
        sa.Column("ends_on", sa.Date(), nullable=False),
        sa.Column("published", sa.Boolean(), nullable=False),
        sa.Column("announced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_fairs"),
        sa.CheckConstraint("name <> ''", name="ck_fairs_name"),
        sa.CheckConstraint("city <> ''", name="ck_fairs_city"),
        sa.CheckConstraint("ends_on >= starts_on", name="ck_fairs_dates"),
        sa.CheckConstraint("ends_on - starts_on < 14", name="ck_fairs_length"),
        # Only what the shop shows can be announced.
        sa.CheckConstraint(
            "announced_at IS NULL OR published", name="ck_fairs_announced_published"
        ),
        schema="site",
    )
    op.create_index(
        "fairs_published_ends_on_idx",
        "fairs",
        ["ends_on"],
        schema="site",
        postgresql_where=sa.text("published"),
    )


def _create_subscriptions() -> None:
    op.create_table(
        "subscriptions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("email", postgresql.CITEXT(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        # The version of the consent wording the visitor agreed to.
        sa.Column("consent", sa.Text(), nullable=False),
        sa.Column("unsubscribe_token", sa.Text(), nullable=False),
        # Only the SHA-256 of the confirmation token, never the token itself.
        sa.Column("confirm_token_hash", sa.Text(), nullable=True),
        sa.Column("confirm_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("confirm_requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_subscriptions"),
        sa.UniqueConstraint("email", name="uq_subscriptions_email"),
        sa.UniqueConstraint("unsubscribe_token", name="uq_subscriptions_unsubscribe_token"),
        sa.UniqueConstraint("confirm_token_hash", name="uq_subscriptions_confirm_token_hash"),
        sa.CheckConstraint("status IN ('pending', 'confirmed')", name="ck_subscriptions_status"),
        sa.CheckConstraint(
            "(status = 'confirmed') = (confirmed_at IS NOT NULL)",
            name="ck_subscriptions_confirmed_at",
        ),
        sa.CheckConstraint(
            "(confirm_token_hash IS NULL) = (confirm_expires_at IS NULL)",
            name="ck_subscriptions_confirm_token",
        ),
        schema="site",
    )


def _create_mailings() -> None:
    op.create_table(
        "mailings",
        sa.Column("fair_id", sa.Uuid(), nullable=False),
        sa.Column("subscription_id", sa.Uuid(), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("fair_id", "subscription_id", name="pk_mailings"),
        sa.ForeignKeyConstraint(
            ["fair_id"], ["site.fairs.id"], name="fk_mailings_fair_id_fairs", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["subscription_id"],
            ["site.subscriptions.id"],
            name="fk_mailings_subscription_id_subscriptions",
            ondelete="CASCADE",
        ),
        schema="site",
    )


def downgrade() -> None:
    op.drop_table("mailings", schema="site")
    op.drop_table("subscriptions", schema="site")
    op.drop_table("fairs", schema="site")
    op.execute("DROP SCHEMA site")
