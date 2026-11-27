"""Tables of the ``newsletter`` schema (created by migration 0035_newsletter).

Constraint names follow ``platform.db.NAMING_CONVENTION``; the migration spells them out.
"""

from sqlalchemy import (
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Table,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.dialects.postgresql import ARRAY

from modellbahn.modules.identity.contracts.accounts import ACCOUNT_REFERENCE
from modellbahn.modules.newsletter.domain.model import SubscriptionStatus
from modellbahn.platform.db import StrEnumType, metadata

SCHEMA = "newsletter"

subscriptions = Table(
    "subscriptions",
    metadata,
    Column("id", Uuid, primary_key=True),
    # Accounts are anonymised, not deleted; the handler of the deletion removes the row.
    Column("account_id", Uuid, ForeignKey(ACCOUNT_REFERENCE, ondelete="CASCADE"), nullable=False),
    Column("status", StrEnumType(SubscriptionStatus), nullable=False),
    Column("consent", Text, nullable=False),
    Column("unsubscribe_token", Text, nullable=False),
    Column("confirm_token_hash", Text),
    Column("confirm_expires_at", DateTime(timezone=True)),
    Column("confirm_requested_at", DateTime(timezone=True), nullable=False),
    Column("confirmed_at", DateTime(timezone=True)),
    Column("created_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint("account_id"),
    UniqueConstraint("unsubscribe_token"),
    UniqueConstraint("confirm_token_hash"),
    CheckConstraint("status IN ('pending', 'confirmed')", name="status"),
    CheckConstraint("(status = 'confirmed') = (confirmed_at IS NOT NULL)", name="confirmed_at"),
    CheckConstraint(
        "(confirm_token_hash IS NULL) = (confirm_expires_at IS NULL)", name="confirm_token"
    ),
    schema=SCHEMA,
)

issues = Table(
    "issues",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("number", Integer, nullable=False),
    Column("issue_date", Date, nullable=False),
    Column("new_since", DateTime(timezone=True), nullable=False),
    Column("new_product_ids", ARRAY(Uuid), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint("number"),
    UniqueConstraint("issue_date"),
    CheckConstraint("number > 0", name="number"),
    schema=SCHEMA,
)

deliveries = Table(
    "deliveries",
    metadata,
    Column(
        "issue_id", Uuid, ForeignKey("newsletter.issues.id", ondelete="CASCADE"), primary_key=True
    ),
    Column(
        "subscription_id",
        Uuid,
        ForeignKey("newsletter.subscriptions.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column("sent_at", DateTime(timezone=True), nullable=False),
    schema=SCHEMA,
)
