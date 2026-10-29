"""SQLAlchemy Core tables of the ``sales`` schema.

They mirror migration ``0003_sales`` exactly, including constraint names;
``tests/integration/test_migrations.py`` compares both.

Cart and order lines name catalogue variants without a foreign key: a variant is not an
aggregate root (KONZEPT §3.1), and an order line keeps what it needs as a frozen copy.
Orders and address books refer to customer accounts by ``(id, kind)``, so only customer
accounts qualify.
"""

from sqlalchemy import (
    CHAR,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    PrimaryKeyConstraint,
    Sequence,
    SmallInteger,
    Table,
    Text,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import CITEXT, ExcludeConstraint

from modellbahn.modules.identity.contracts.accounts import CUSTOMER_KIND, CUSTOMER_REFERENCE
from modellbahn.modules.sales.domain.model import (
    CancelReason,
    OrderStatus,
    PaymentStatus,
    SalesChannel,
)
from modellbahn.platform.db import StrEnumType, metadata

SCHEMA = "sales"

# The serial part of the order numbers (MB-2026-00042).
order_number_seq = Sequence("order_number_seq", schema=SCHEMA, metadata=metadata)

carts = Table(
    "carts",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Column("expires_at", DateTime(timezone=True), nullable=False),
    CheckConstraint("expires_at > updated_at", name="expires_after_update"),
    Index("carts_expires_idx", "expires_at"),
    schema=SCHEMA,
)

cart_lines = Table(
    "cart_lines",
    metadata,
    Column("cart_id", Uuid, ForeignKey(carts.c.id, ondelete="CASCADE"), nullable=False),
    Column("variant_id", Uuid, nullable=False),
    Column("quantity", SmallInteger, nullable=False),
    Column("added_at", DateTime(timezone=True), nullable=False),
    PrimaryKeyConstraint("cart_id", "variant_id"),
    CheckConstraint("quantity BETWEEN 1 AND 99", name="quantity_range"),
    schema=SCHEMA,
)

orders = Table(
    "orders",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("number", Text, nullable=False, unique=True),
    # The status link of guests; long and random, so it cannot be guessed.
    Column("public_token", Text, nullable=False, unique=True),
    Column("status", StrEnumType(OrderStatus), nullable=False),
    Column("customer_account_id", Uuid),
    Column("customer_kind", Text, nullable=False, server_default=text(f"'{CUSTOMER_KIND}'")),
    Column("email", CITEXT, nullable=False),
    Column("ship_recipient", Text, nullable=False),
    Column("ship_street", Text, nullable=False),
    Column("ship_postal_code", Text, nullable=False),
    Column("ship_city", Text, nullable=False),
    Column("ship_country", CHAR(2), nullable=False),
    Column("subtotal_cents", Integer, nullable=False),
    Column("shipping_cents", Integer, nullable=False),
    Column("total_cents", Integer, nullable=False),
    Column("tax_cents", Integer, nullable=False),
    # Idempotency-Key of the checkout and a hash of its request (see application.checkout).
    Column("checkout_key", Uuid, nullable=False, unique=True),
    Column("checkout_fingerprint", CHAR(64), nullable=False),
    Column("placed_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Column("paid_at", DateTime(timezone=True)),
    Column("shipped_at", DateTime(timezone=True)),
    Column("cancelled_at", DateTime(timezone=True)),
    Column("cancel_reason", StrEnumType(CancelReason)),
    Column("cancel_note", Text, nullable=False, server_default=text("''")),
    Column("carrier", Text, nullable=False, server_default=text("''")),
    Column("tracking_number", Text, nullable=False, server_default=text("''")),
    # Where the order came from; a marketplace order carries the marketplace's number.
    Column("channel", StrEnumType(SalesChannel), nullable=False, server_default=text("'shop'")),
    Column("external_ref", Text),
    CheckConstraint("status IN ('pending_payment', 'paid', 'shipped', 'cancelled')", name="status"),
    CheckConstraint("channel IN ('shop', 'ebay')", name="channel"),
    CheckConstraint("(channel = 'shop') = (external_ref IS NULL)", name="external_ref"),
    CheckConstraint("number ~ '^MB-[0-9]{4}-[0-9]{5,}$'", name="number_format"),
    CheckConstraint(f"customer_kind = '{CUSTOMER_KIND}'", name="customer_kind"),
    CheckConstraint("ship_country ~ '^[A-Z]{2}$'", name="ship_country_format"),
    CheckConstraint(
        "subtotal_cents >= 0 AND shipping_cents >= 0 AND tax_cents >= 0",
        name="amounts_non_negative",
    ),
    CheckConstraint("total_cents = subtotal_cents + shipping_cents", name="total_is_sum"),
    CheckConstraint("tax_cents <= total_cents", name="tax_within_total"),
    CheckConstraint("checkout_fingerprint ~ '^[0-9a-f]{64}$'", name="checkout_fingerprint_format"),
    # Each state carries the time it was reached, and only then.
    CheckConstraint(
        "status NOT IN ('paid', 'shipped') OR paid_at IS NOT NULL", name="paid_has_time"
    ),
    CheckConstraint("(status = 'shipped') = (shipped_at IS NOT NULL)", name="shipped_at"),
    CheckConstraint(
        "(status = 'cancelled') = (cancelled_at IS NOT NULL AND cancel_reason IS NOT NULL)",
        name="cancelled_at",
    ),
    CheckConstraint(
        "cancel_reason IS NULL OR "
        "cancel_reason IN ('payment_timeout', 'by_shop', 'by_marketplace')",
        name="cancel_reason",
    ),
    ForeignKeyConstraint(
        ["customer_account_id", "customer_kind"], list(CUSTOMER_REFERENCE), ondelete="RESTRICT"
    ),
    Index(
        "orders_customer_idx",
        "customer_account_id",
        "placed_at",
        postgresql_where=text("customer_account_id IS NOT NULL"),
    ),
    # Adoption looks up guest orders by address.
    Index("orders_guest_email_idx", "email", postgresql_where=text("customer_account_id IS NULL")),
    Index("orders_placed_idx", "placed_at", "id"),
    # One order per marketplace sale.
    Index(
        "orders_external_ref_idx",
        "channel",
        "external_ref",
        unique=True,
        postgresql_where=text("external_ref IS NOT NULL"),
    ),
    # The periodic job looks for orders whose payment is overdue.
    Index("orders_pending_idx", "placed_at", postgresql_where=text("status = 'pending_payment'")),
    schema=SCHEMA,
)

order_lines = Table(
    "order_lines",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("order_id", Uuid, ForeignKey(orders.c.id, ondelete="CASCADE"), nullable=False),
    Column("position", SmallInteger, nullable=False),
    Column("variant_id", Uuid, nullable=False),
    Column("product_slug", Text, nullable=False),
    Column("sku", Text, nullable=False),
    Column("title", Text, nullable=False),
    Column("scale_code", Text, nullable=False),
    Column("finish_code", Text, nullable=False),
    Column("unit_price_cents", Integer, nullable=False),
    Column("quantity", SmallInteger, nullable=False),
    Column("line_total_cents", Integer, nullable=False),
    # The photo shown with the line; the image may be gone one day, the line stays.
    Column("image_asset_id", Uuid),
    CheckConstraint("quantity BETWEEN 1 AND 99", name="quantity_range"),
    CheckConstraint("unit_price_cents >= 0", name="price_non_negative"),
    CheckConstraint("line_total_cents = unit_price_cents * quantity", name="line_total"),
    CheckConstraint("position >= 0", name="position_non_negative"),
    Index("order_lines_order_idx", "order_id", "position", unique=True),
    schema=SCHEMA,
)

payments = Table(
    "payments",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("order_id", Uuid, ForeignKey(orders.c.id, ondelete="CASCADE"), nullable=False),
    Column("provider", Text, nullable=False),
    Column("provider_ref", Text, nullable=False),
    Column("status", StrEnumType(PaymentStatus), nullable=False),
    Column("amount_cents", Integer, nullable=False),
    # Idempotency-Key of the payment request and a hash of the request.
    Column("idempotency_key", Uuid, nullable=False, unique=True),
    Column("request_fingerprint", CHAR(64), nullable=False),
    Column("failure_code", Text),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    CheckConstraint("status IN ('captured', 'failed', 'refunded')", name="status"),
    CheckConstraint("amount_cents >= 0", name="amount_non_negative"),
    CheckConstraint("request_fingerprint ~ '^[0-9a-f]{64}$'", name="request_fingerprint_format"),
    CheckConstraint("(status = 'failed') = (failure_code IS NOT NULL)", name="failure_code"),
    Index("payments_provider_ref_idx", "provider", "provider_ref", unique=True),
    Index("payments_order_idx", "order_id"),
    schema=SCHEMA,
)

customer_addresses = Table(
    "customer_addresses",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("account_id", Uuid, nullable=False),
    Column("account_kind", Text, nullable=False, server_default=text(f"'{CUSTOMER_KIND}'")),
    Column("label", Text, nullable=False, server_default=text("''")),
    Column("recipient", Text, nullable=False),
    Column("street", Text, nullable=False),
    Column("postal_code", Text, nullable=False),
    Column("city", Text, nullable=False),
    Column("country_code", CHAR(2), nullable=False),
    Column("is_default", Boolean, nullable=False, server_default=text("false")),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    CheckConstraint(f"account_kind = '{CUSTOMER_KIND}'", name="account_kind"),
    CheckConstraint("country_code ~ '^[A-Z]{2}$'", name="country_code_format"),
    # Deleting an account removes its book first (sales reacts to identity.account.deleted).
    ForeignKeyConstraint(
        ["account_id", "account_kind"], list(CUSTOMER_REFERENCE), ondelete="RESTRICT"
    ),
    # At most one default per book, checked at commit: switching it is a single step.
    ExcludeConstraint(
        ("account_id", "="),
        name="ex_customer_addresses_one_default",
        using="btree",
        where=text("is_default"),
        deferrable=True,
        initially="DEFERRED",
    ),
    Index("customer_addresses_account_idx", "account_id"),
    schema=SCHEMA,
)
