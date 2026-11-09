"""Tables of the ``ai`` schema (created by migration 0015_ai).

Constraint names follow ``platform.db.NAMING_CONVENTION``; the migration spells them out.
"""

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    Table,
    Text,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB

from modellbahn.modules.ai.domain.model import FailureReason, Review, RunStatus
from modellbahn.modules.catalog.contracts.copy_facts import PRODUCT_REFERENCE
from modellbahn.modules.identity.contracts.accounts import ACCOUNT_REFERENCE
from modellbahn.platform.db import StrEnumType, metadata

SCHEMA = "ai"

runs = Table(
    "runs",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("task", Text, nullable=False),
    # A deleted product leaves its runs behind: they hold what the month's budget spent.
    Column("product_id", Uuid, ForeignKey(PRODUCT_REFERENCE, ondelete="SET NULL")),
    Column("product_name", Text, nullable=False),
    Column("requested_by", Uuid, ForeignKey(ACCOUNT_REFERENCE, ondelete="RESTRICT")),
    Column("status", StrEnumType(RunStatus), nullable=False),
    Column("review", StrEnumType(Review), nullable=False),
    Column("prompt_version", Text, nullable=False, server_default=text("''")),
    Column("model", Text, nullable=False, server_default=text("''")),
    Column("input", JSONB, nullable=False, server_default=text("'{}'::jsonb")),
    Column("output", JSONB),
    Column("warnings", JSONB, nullable=False, server_default=text("'[]'::jsonb")),
    Column("failure", StrEnumType(FailureReason)),
    Column("failure_detail", Text, nullable=False, server_default=text("''")),
    Column("attempts", SmallInteger, nullable=False, server_default=text("0")),
    Column("input_tokens", Integer, nullable=False, server_default=text("0")),
    Column("output_tokens", Integer, nullable=False, server_default=text("0")),
    Column("cache_read_tokens", Integer, nullable=False, server_default=text("0")),
    Column("cache_write_tokens", Integer, nullable=False, server_default=text("0")),
    Column("cost_micro_usd", BigInteger, nullable=False, server_default=text("0")),
    Column("applied_fields", JSONB, nullable=False, server_default=text("'[]'::jsonb")),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("started_at", DateTime(timezone=True)),
    Column("finished_at", DateTime(timezone=True)),
    Column("reviewed_at", DateTime(timezone=True)),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    CheckConstraint("task IN ('product_copy')", name="task"),
    CheckConstraint("status IN ('queued', 'running', 'done', 'failed')", name="status"),
    CheckConstraint("review IN ('pending', 'applied', 'discarded')", name="review"),
    CheckConstraint(
        "failure IS NULL OR failure IN ('budget_exceeded', 'refused', 'truncated',"
        " 'invalid_output', 'product_gone', 'provider_error', 'abandoned', 'disabled')",
        name="failure",
    ),
    CheckConstraint("(status = 'failed') = (failure IS NOT NULL)", name="failure_when_failed"),
    CheckConstraint("(status = 'done') = (output IS NOT NULL)", name="output_when_done"),
    CheckConstraint("review <> 'applied' OR status = 'done'", name="applied_when_done"),
    CheckConstraint(
        "attempts >= 0 AND input_tokens >= 0 AND output_tokens >= 0 AND cache_read_tokens >= 0"
        " AND cache_write_tokens >= 0 AND cost_micro_usd >= 0",
        name="counts",
    ),
    # The worker looks for the oldest run to write; the Stellwerk for a product's runs.
    Index(
        "runs_due_idx",
        "created_at",
        postgresql_where=text("status IN ('queued', 'running')"),
    ),
    Index("runs_product_idx", "product_id", "created_at"),
    # The month's spending.
    Index("runs_created_idx", "created_at"),
    schema=SCHEMA,
)
