"""Tables of the ``marketplace`` schema (created by migration 0008_marketplace).

Constraint names follow ``platform.db.NAMING_CONVENTION``; the migration spells them out.

Products, variants and categories are named by id without foreign keys: a draft product
may be deleted while it has a listing (the next sync ends it), and the mapping of a
category that is gone is simply never used. Orders of the sales module are created from
``marketplace_orders`` afterwards, with the id chosen here, so there is no key either.
"""

from sqlalchemy import (
    CHAR,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
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

from modellbahn.modules.marketplace.domain.model import (
    ConnectionStatus,
    ListingStatus,
    MarketplaceOrderStatus,
)
from modellbahn.platform.db import StrEnumType, metadata

SCHEMA = "marketplace"

ebay_account = Table(
    "ebay_account",
    metadata,
    Column("channel", Text, primary_key=True),
    Column("status", StrEnumType(ConnectionStatus), nullable=False),
    Column("seller_name", Text, nullable=False, server_default=text("''")),
    # Encrypted with MB_EBAY_TOKEN_KEY; empty while not connected.
    Column("access_token", Text, nullable=False, server_default=text("''")),
    Column("access_expires_at", DateTime(timezone=True)),
    Column("refresh_token", Text, nullable=False, server_default=text("''")),
    Column("refresh_expires_at", DateTime(timezone=True)),
    # Only the SHA-256 of the state sent to eBay's consent page.
    Column("connect_state_hash", CHAR(64)),
    Column("connect_state_expires_at", DateTime(timezone=True)),
    Column("fulfillment_policy_id", Text, nullable=False, server_default=text("''")),
    Column("payment_policy_id", Text, nullable=False, server_default=text("''")),
    Column("return_policy_id", Text, nullable=False, server_default=text("''")),
    Column("location_ready", Boolean, nullable=False, server_default=text("false")),
    Column("price_markup_percent", SmallInteger, nullable=False, server_default=text("0")),
    Column("made_to_order_quantity", SmallInteger, nullable=False, server_default=text("3")),
    Column("orders_checked_until", DateTime(timezone=True)),
    Column("connected_at", DateTime(timezone=True)),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    CheckConstraint("channel = 'ebay'", name="channel"),
    CheckConstraint("status IN ('disconnected', 'connected', 'expired')", name="status"),
    CheckConstraint("price_markup_percent BETWEEN 0 AND 100", name="markup_range"),
    CheckConstraint("made_to_order_quantity BETWEEN 1 AND 20", name="made_to_order_range"),
    CheckConstraint(
        "(status = 'connected') = (refresh_token <> '' AND connected_at IS NOT NULL)",
        name="connected_has_token",
    ),
    schema=SCHEMA,
)

category_map = Table(
    "category_map",
    metadata,
    Column("category_id", Uuid, primary_key=True),
    Column("ebay_category_id", Text, nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    CheckConstraint("ebay_category_id ~ '^[0-9]{1,10}$'", name="ebay_category_format"),
    schema=SCHEMA,
)

listings = Table(
    "listings",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("product_id", Uuid, nullable=False),
    Column("scale_code", Text, nullable=False),
    Column("group_key", Text, nullable=False, unique=True),
    Column("wanted", Boolean, nullable=False),
    Column("status", StrEnumType(ListingStatus), nullable=False),
    Column("external_id", Text, nullable=False, server_default=text("''")),
    Column("needs_sync", Boolean, nullable=False),
    Column("error_code", Text),
    Column("error_message", Text, nullable=False, server_default=text("''")),
    Column("synced_at", DateTime(timezone=True)),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint("product_id", "scale_code"),
    CheckConstraint("status IN ('pending', 'active', 'failed', 'ended')", name="status"),
    CheckConstraint("(status = 'failed') = (error_code IS NOT NULL)", name="failed_has_error"),
    # The worker looks for listings due for a sync.
    Index("listings_needs_sync_idx", "updated_at", postgresql_where=text("needs_sync")),
    schema=SCHEMA,
)

listing_items = Table(
    "listing_items",
    metadata,
    Column("listing_id", Uuid, ForeignKey(listings.c.id, ondelete="CASCADE"), nullable=False),
    Column("sku", Text, nullable=False),
    Column("variant_id", Uuid, nullable=False),
    Column("offer_id", Text, nullable=False, server_default=text("''")),
    Column("quantity", Integer, nullable=False),
    Column("price_cents", Integer, nullable=False),
    PrimaryKeyConstraint("listing_id", "sku"),
    CheckConstraint("quantity >= 0", name="quantity_non_negative"),
    CheckConstraint("price_cents >= 0", name="price_non_negative"),
    # A stock change of a variant marks its listings for a sync.
    Index("listing_items_variant_idx", "variant_id"),
    schema=SCHEMA,
)

marketplace_orders = Table(
    "marketplace_orders",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("channel", Text, nullable=False),
    Column("external_id", Text, nullable=False),
    Column("order_id", Uuid, nullable=False, unique=True),
    Column("status", StrEnumType(MarketplaceOrderStatus), nullable=False),
    Column("buyer_name", Text, nullable=False),
    Column("email", Text, nullable=False),
    Column("recipient", Text, nullable=False),
    Column("street", Text, nullable=False),
    Column("postal_code", Text, nullable=False),
    Column("city", Text, nullable=False),
    Column("country_code", Text, nullable=False),
    Column("shipping_cents", Integer, nullable=False),
    Column("total_cents", Integer, nullable=False),
    Column("paid_at", DateTime(timezone=True), nullable=False),
    Column("problem", Text, nullable=False, server_default=text("''")),
    Column("received_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Column("shipped_reported_at", DateTime(timezone=True)),
    Column("buyer_erased_at", DateTime(timezone=True)),
    UniqueConstraint("channel", "external_id"),
    CheckConstraint("channel = 'ebay'", name="channel"),
    CheckConstraint("status IN ('received', 'rejected', 'shipped', 'cancelled')", name="status"),
    CheckConstraint("shipping_cents >= 0 AND total_cents >= 0", name="amounts_non_negative"),
    CheckConstraint("(status = 'rejected') <= (problem <> '')", name="rejected_has_problem"),
    CheckConstraint(
        "(status = 'shipped') = (shipped_reported_at IS NOT NULL)", name="shipped_reported"
    ),
    Index("marketplace_orders_received_idx", "received_at", "id"),
    # eBay's notifications of closed accounts name the buyer; most name no buyer of ours.
    Index(
        "marketplace_orders_buyer_idx",
        "channel",
        text("lower(buyer_name)"),
        postgresql_where=text("buyer_erased_at IS NULL"),
    ),
    schema=SCHEMA,
)

marketplace_order_lines = Table(
    "marketplace_order_lines",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column(
        "marketplace_order_id",
        Uuid,
        # Named here: the conventional name would pass PostgreSQL's 63 characters.
        ForeignKey(
            marketplace_orders.c.id,
            ondelete="CASCADE",
            name="fk_marketplace_order_lines_marketplace_orders",
        ),
        nullable=False,
    ),
    Column("position", SmallInteger, nullable=False),
    Column("line_ref", Text, nullable=False),
    Column("sku", Text, nullable=False),
    Column("variant_id", Uuid),
    Column("title", Text, nullable=False),
    Column("quantity", SmallInteger, nullable=False),
    Column("unit_price_cents", Integer, nullable=False),
    UniqueConstraint("marketplace_order_id", "position"),
    CheckConstraint("quantity BETWEEN 1 AND 999", name="quantity_range"),
    CheckConstraint("unit_price_cents >= 0", name="price_non_negative"),
    schema=SCHEMA,
)

test_sales = Table(
    "test_sales",
    metadata,
    # Sales on the built-in test marketplace (MB_EBAY_MODE=test), as eBay would report them.
    Column("id", Uuid, primary_key=True),
    Column("external_id", Text, nullable=False, unique=True),
    Column("sku", Text, nullable=False),
    Column("quantity", SmallInteger, nullable=False),
    Column("unit_price_cents", Integer, nullable=False),
    Column("shipping_cents", Integer, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("modified_at", DateTime(timezone=True), nullable=False),
    Column("cancelled_at", DateTime(timezone=True)),
    CheckConstraint("quantity BETWEEN 1 AND 99", name="quantity_range"),
    Index("test_sales_modified_idx", "modified_at"),
    schema=SCHEMA,
)
