"""Tables of the ``site`` schema (created by migration 0006_site).

Constraint names follow ``platform.db.NAMING_CONVENTION``; the migration spells them out.
"""

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Table,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import CITEXT

from modellbahn.modules.site.domain.model import SubscriptionStatus
from modellbahn.platform.db import StrEnumType, metadata

SCHEMA = "site"

fairs = Table(
    "fairs",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("name", Text, nullable=False),
    Column("venue", Text, nullable=False),
    Column("street", Text, nullable=False),
    Column("postal_code", Text, nullable=False),
    Column("city", Text, nullable=False),
    Column("booth", Text, nullable=False),
    Column("hours", Text, nullable=False),
    Column("website_url", Text, nullable=False),
    Column("note", Text, nullable=False),
    Column("starts_on", Date, nullable=False),
    Column("ends_on", Date, nullable=False),
    Column("published", Boolean, nullable=False),
    Column("announced_at", DateTime(timezone=True)),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    CheckConstraint("name <> ''", name="name"),
    CheckConstraint("city <> ''", name="city"),
    CheckConstraint("ends_on >= starts_on", name="dates"),
    CheckConstraint("ends_on - starts_on < 14", name="length"),
    CheckConstraint("announced_at IS NULL OR published", name="announced_published"),
    # The shop asks for published fairs by their last day.
    Index("fairs_published_ends_on_idx", "ends_on", postgresql_where=text("published")),
    schema=SCHEMA,
)

subscriptions = Table(
    "subscriptions",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("email", CITEXT, nullable=False),
    Column("status", StrEnumType(SubscriptionStatus), nullable=False),
    Column("consent", Text, nullable=False),
    Column("unsubscribe_token", Text, nullable=False),
    Column("confirm_token_hash", Text),
    Column("confirm_expires_at", DateTime(timezone=True)),
    Column("confirm_requested_at", DateTime(timezone=True), nullable=False),
    Column("confirmed_at", DateTime(timezone=True)),
    Column("created_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint("email"),
    UniqueConstraint("unsubscribe_token"),
    UniqueConstraint("confirm_token_hash"),
    CheckConstraint("status IN ('pending', 'confirmed')", name="status"),
    CheckConstraint("(status = 'confirmed') = (confirmed_at IS NOT NULL)", name="confirmed_at"),
    CheckConstraint(
        "(confirm_token_hash IS NULL) = (confirm_expires_at IS NULL)", name="confirm_token"
    ),
    schema=SCHEMA,
)

mailings = Table(
    "mailings",
    metadata,
    Column("fair_id", Uuid, ForeignKey("site.fairs.id", ondelete="CASCADE"), primary_key=True),
    Column(
        "subscription_id",
        Uuid,
        ForeignKey("site.subscriptions.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column("sent_at", DateTime(timezone=True), nullable=False),
    schema=SCHEMA,
)
