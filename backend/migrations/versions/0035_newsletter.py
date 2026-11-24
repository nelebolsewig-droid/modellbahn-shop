"""The newsletter for customer accounts (ADR 0049).

Written by hand like the migrations before.

- ``newsletter.subscriptions``: one per customer account, double opt-in like the fair news;
  no address is copied, the issues go to the account's address.
- ``newsletter.issues``: one per issue day at most, with the models new since the last.
- ``newsletter.deliveries``: which reader got which issue (never twice).

Revision ID: 0035
Revises: 0034
Create Date: 2026-11-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0035"
down_revision: str | None = "0034"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA newsletter")
    op.create_table(
        "subscriptions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        # The version of the consent wording the customer agreed to.
        sa.Column("consent", sa.Text(), nullable=False),
        sa.Column("unsubscribe_token", sa.Text(), nullable=False),
        # Only the SHA-256 of the confirmation token, never the token itself.
        sa.Column("confirm_token_hash", sa.Text(), nullable=True),
        sa.Column("confirm_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("confirm_requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_subscriptions"),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["identity.accounts.id"],
            name="fk_subscriptions_account_id_accounts",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("account_id", name="uq_subscriptions_account_id"),
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
        schema="newsletter",
    )
    op.create_table(
        "issues",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("issue_date", sa.Date(), nullable=False),
        sa.Column("new_since", sa.DateTime(timezone=True), nullable=False),
        sa.Column("new_product_ids", postgresql.ARRAY(sa.Uuid()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_issues"),
        sa.UniqueConstraint("number", name="uq_issues_number"),
        sa.UniqueConstraint("issue_date", name="uq_issues_issue_date"),
        sa.CheckConstraint("number > 0", name="ck_issues_number"),
        schema="newsletter",
    )
    op.create_table(
        "deliveries",
        sa.Column("issue_id", sa.Uuid(), nullable=False),
        sa.Column("subscription_id", sa.Uuid(), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("issue_id", "subscription_id", name="pk_deliveries"),
        sa.ForeignKeyConstraint(
            ["issue_id"],
            ["newsletter.issues.id"],
            name="fk_deliveries_issue_id_issues",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["subscription_id"],
            ["newsletter.subscriptions.id"],
            name="fk_deliveries_subscription_id_subscriptions",
            ondelete="CASCADE",
        ),
        schema="newsletter",
    )


def downgrade() -> None:
    op.drop_table("deliveries", schema="newsletter")
    op.drop_table("issues", schema="newsletter")
    op.drop_table("subscriptions", schema="newsletter")
    op.execute("DROP SCHEMA newsletter")
