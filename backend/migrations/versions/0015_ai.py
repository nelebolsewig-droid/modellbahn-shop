"""Product text drafts from the language model (ADR 0021).

Written by hand like the migrations before; constraint names follow the naming
convention of ``modellbahn.platform.db``.

- ``ai.runs`` holds one row per requested draft: the facts the model saw, its answer,
  the warnings of the check, tokens and cost, and what people did with the draft.
- A deleted product leaves its runs behind (``product_id`` turns NULL): they hold what
  the month's budget spent.

Revision ID: 0015
Revises: 0014
Create Date: 2026-11-08
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_FAILURES = (
    "'budget_exceeded', 'refused', 'truncated', 'invalid_output', 'product_gone',"
    " 'provider_error', 'abandoned', 'disabled'"
)


def upgrade() -> None:
    op.execute("CREATE SCHEMA ai")
    op.create_table(
        "runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("task", sa.Text(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=True),
        sa.Column("product_name", sa.Text(), nullable=False),
        sa.Column("requested_by", sa.Uuid(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("review", sa.Text(), nullable=False),
        sa.Column("prompt_version", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column("model", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column(
            "input",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("output", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "warnings",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("failure", sa.Text(), nullable=True),
        sa.Column("failure_detail", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column("attempts", sa.SmallInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column("input_tokens", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("output_tokens", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("cache_read_tokens", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("cache_write_tokens", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("cost_micro_usd", sa.BigInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "applied_fields",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_runs"),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["catalog.products.id"],
            name="fk_runs_product_id_products",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["requested_by"],
            ["identity.accounts.id"],
            name="fk_runs_requested_by_accounts",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint("task IN ('product_copy')", name="ck_runs_task"),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'done', 'failed')", name="ck_runs_status"
        ),
        sa.CheckConstraint("review IN ('pending', 'applied', 'discarded')", name="ck_runs_review"),
        sa.CheckConstraint(f"failure IS NULL OR failure IN ({_FAILURES})", name="ck_runs_failure"),
        sa.CheckConstraint(
            "(status = 'failed') = (failure IS NOT NULL)", name="ck_runs_failure_when_failed"
        ),
        sa.CheckConstraint(
            "(status = 'done') = (output IS NOT NULL)", name="ck_runs_output_when_done"
        ),
        sa.CheckConstraint(
            "review <> 'applied' OR status = 'done'", name="ck_runs_applied_when_done"
        ),
        sa.CheckConstraint(
            "attempts >= 0 AND input_tokens >= 0 AND output_tokens >= 0"
            " AND cache_read_tokens >= 0 AND cache_write_tokens >= 0 AND cost_micro_usd >= 0",
            name="ck_runs_counts",
        ),
        schema="ai",
    )
    op.create_index(
        "runs_due_idx",
        "runs",
        ["created_at"],
        schema="ai",
        postgresql_where=sa.text("status IN ('queued', 'running')"),
    )
    op.create_index("runs_product_idx", "runs", ["product_id", "created_at"], schema="ai")
    op.create_index("runs_created_idx", "runs", ["created_at"], schema="ai")


def downgrade() -> None:
    op.drop_table("runs", schema="ai")
    op.execute("DROP SCHEMA ai")
