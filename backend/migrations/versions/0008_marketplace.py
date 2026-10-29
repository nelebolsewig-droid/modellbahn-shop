"""Marketplace: eBay as a second sales channel (ADR 0014).

- ``sales.orders`` learns where an order came from (``channel``) and the marketplace's
  number of it (``external_ref``); a marketplace may cancel an order (``by_marketplace``).
- The ``marketplace`` schema keeps the connection to eBay with its settings, the mapping
  of categories to eBay's, the listings with their variants, the orders as eBay reported
  them, and the sales of the built-in test marketplace.

Written by hand like the migrations before; constraint names follow the naming
convention of ``modellbahn.platform.db``.

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CANCEL_REASONS_BEFORE = "cancel_reason IS NULL OR cancel_reason IN ('payment_timeout', 'by_shop')"
_CANCEL_REASONS = (
    "cancel_reason IS NULL OR cancel_reason IN ('payment_timeout', 'by_shop', 'by_marketplace')"
)


def upgrade() -> None:
    _extend_sales_orders()
    op.execute("CREATE SCHEMA marketplace")
    _create_ebay_account()
    _create_category_map()
    _create_listings()
    _create_marketplace_orders()
    _create_test_sales()


def _extend_sales_orders() -> None:
    op.add_column(
        "orders",
        sa.Column("channel", sa.Text(), server_default=sa.text("'shop'"), nullable=False),
        schema="sales",
    )
    op.add_column("orders", sa.Column("external_ref", sa.Text(), nullable=True), schema="sales")
    op.create_check_constraint(
        "ck_orders_channel", "orders", "channel IN ('shop', 'ebay')", schema="sales"
    )
    op.create_check_constraint(
        "ck_orders_external_ref",
        "orders",
        "(channel = 'shop') = (external_ref IS NULL)",
        schema="sales",
    )
    op.create_index(
        "orders_external_ref_idx",
        "orders",
        ["channel", "external_ref"],
        unique=True,
        schema="sales",
        postgresql_where=sa.text("external_ref IS NOT NULL"),
    )
    op.drop_constraint("ck_orders_cancel_reason", "orders", schema="sales", type_="check")
    op.create_check_constraint("ck_orders_cancel_reason", "orders", _CANCEL_REASONS, schema="sales")


def _create_ebay_account() -> None:
    op.create_table(
        "ebay_account",
        sa.Column("channel", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("seller_name", sa.Text(), server_default=sa.text("''"), nullable=False),
        # Encrypted with MB_EBAY_TOKEN_KEY; empty while not connected.
        sa.Column("access_token", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column("access_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("refresh_token", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column("refresh_expires_at", sa.DateTime(timezone=True), nullable=True),
        # Only the SHA-256 of the state sent to eBay's consent page.
        sa.Column("connect_state_hash", sa.CHAR(64), nullable=True),
        sa.Column("connect_state_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("fulfillment_policy_id", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column("payment_policy_id", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column("return_policy_id", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column("location_ready", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column(
            "price_markup_percent", sa.SmallInteger(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column(
            "made_to_order_quantity",
            sa.SmallInteger(),
            server_default=sa.text("3"),
            nullable=False,
        ),
        sa.Column("orders_checked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("connected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("channel", name="pk_ebay_account"),
        sa.CheckConstraint("channel = 'ebay'", name="ck_ebay_account_channel"),
        sa.CheckConstraint(
            "status IN ('disconnected', 'connected', 'expired')", name="ck_ebay_account_status"
        ),
        sa.CheckConstraint(
            "price_markup_percent BETWEEN 0 AND 100", name="ck_ebay_account_markup_range"
        ),
        sa.CheckConstraint(
            "made_to_order_quantity BETWEEN 1 AND 20", name="ck_ebay_account_made_to_order_range"
        ),
        sa.CheckConstraint(
            "(status = 'connected') = (refresh_token <> '' AND connected_at IS NOT NULL)",
            name="ck_ebay_account_connected_has_token",
        ),
        schema="marketplace",
    )


def _create_category_map() -> None:
    op.create_table(
        "category_map",
        sa.Column("category_id", sa.Uuid(), nullable=False),
        sa.Column("ebay_category_id", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("category_id", name="pk_category_map"),
        sa.CheckConstraint(
            "ebay_category_id ~ '^[0-9]{1,10}$'", name="ck_category_map_ebay_category_format"
        ),
        schema="marketplace",
    )


def _create_listings() -> None:
    op.create_table(
        "listings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("scale_code", sa.Text(), nullable=False),
        sa.Column("group_key", sa.Text(), nullable=False),
        sa.Column("wanted", sa.Boolean(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("external_id", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column("needs_sync", sa.Boolean(), nullable=False),
        sa.Column("error_code", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column("synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_listings"),
        sa.UniqueConstraint("group_key", name="uq_listings_group_key"),
        sa.UniqueConstraint("product_id", "scale_code", name="uq_listings_product_id_scale_code"),
        sa.CheckConstraint(
            "status IN ('pending', 'active', 'failed', 'ended')", name="ck_listings_status"
        ),
        sa.CheckConstraint(
            "(status = 'failed') = (error_code IS NOT NULL)", name="ck_listings_failed_has_error"
        ),
        schema="marketplace",
    )
    op.create_index(
        "listings_needs_sync_idx",
        "listings",
        ["updated_at"],
        schema="marketplace",
        postgresql_where=sa.text("needs_sync"),
    )
    op.create_table(
        "listing_items",
        sa.Column("listing_id", sa.Uuid(), nullable=False),
        sa.Column("sku", sa.Text(), nullable=False),
        sa.Column("variant_id", sa.Uuid(), nullable=False),
        sa.Column("offer_id", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("price_cents", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("listing_id", "sku", name="pk_listing_items"),
        sa.ForeignKeyConstraint(
            ["listing_id"],
            ["marketplace.listings.id"],
            name="fk_listing_items_listing_id_listings",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint("quantity >= 0", name="ck_listing_items_quantity_non_negative"),
        sa.CheckConstraint("price_cents >= 0", name="ck_listing_items_price_non_negative"),
        schema="marketplace",
    )
    op.create_index(
        "listing_items_variant_idx", "listing_items", ["variant_id"], schema="marketplace"
    )


def _create_marketplace_orders() -> None:
    op.create_table(
        "marketplace_orders",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("channel", sa.Text(), nullable=False),
        sa.Column("external_id", sa.Text(), nullable=False),
        sa.Column("order_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("buyer_name", sa.Text(), nullable=False),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("recipient", sa.Text(), nullable=False),
        sa.Column("street", sa.Text(), nullable=False),
        sa.Column("postal_code", sa.Text(), nullable=False),
        sa.Column("city", sa.Text(), nullable=False),
        sa.Column("country_code", sa.Text(), nullable=False),
        sa.Column("shipping_cents", sa.Integer(), nullable=False),
        sa.Column("total_cents", sa.Integer(), nullable=False),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("problem", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("shipped_reported_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_marketplace_orders"),
        sa.UniqueConstraint("order_id", name="uq_marketplace_orders_order_id"),
        sa.UniqueConstraint(
            "channel", "external_id", name="uq_marketplace_orders_channel_external_id"
        ),
        sa.CheckConstraint("channel = 'ebay'", name="ck_marketplace_orders_channel"),
        sa.CheckConstraint(
            "status IN ('received', 'rejected', 'shipped', 'cancelled')",
            name="ck_marketplace_orders_status",
        ),
        sa.CheckConstraint(
            "shipping_cents >= 0 AND total_cents >= 0",
            name="ck_marketplace_orders_amounts_non_negative",
        ),
        sa.CheckConstraint(
            "(status = 'rejected') <= (problem <> '')",
            name="ck_marketplace_orders_rejected_has_problem",
        ),
        sa.CheckConstraint(
            "(status = 'shipped') = (shipped_reported_at IS NOT NULL)",
            name="ck_marketplace_orders_shipped_reported",
        ),
        schema="marketplace",
    )
    op.create_index(
        "marketplace_orders_received_idx",
        "marketplace_orders",
        ["received_at", "id"],
        schema="marketplace",
    )
    op.create_table(
        "marketplace_order_lines",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("marketplace_order_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.SmallInteger(), nullable=False),
        sa.Column("line_ref", sa.Text(), nullable=False),
        sa.Column("sku", sa.Text(), nullable=False),
        sa.Column("variant_id", sa.Uuid(), nullable=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("quantity", sa.SmallInteger(), nullable=False),
        sa.Column("unit_price_cents", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_marketplace_order_lines"),
        sa.ForeignKeyConstraint(
            ["marketplace_order_id"],
            ["marketplace.marketplace_orders.id"],
            name="fk_marketplace_order_lines_marketplace_orders",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "marketplace_order_id",
            "position",
            name="uq_marketplace_order_lines_marketplace_order_id_position",
        ),
        sa.CheckConstraint(
            "quantity BETWEEN 1 AND 999", name="ck_marketplace_order_lines_quantity_range"
        ),
        sa.CheckConstraint(
            "unit_price_cents >= 0", name="ck_marketplace_order_lines_price_non_negative"
        ),
        schema="marketplace",
    )


def _create_test_sales() -> None:
    op.create_table(
        "test_sales",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("external_id", sa.Text(), nullable=False),
        sa.Column("sku", sa.Text(), nullable=False),
        sa.Column("quantity", sa.SmallInteger(), nullable=False),
        sa.Column("unit_price_cents", sa.Integer(), nullable=False),
        sa.Column("shipping_cents", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("modified_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_test_sales"),
        sa.UniqueConstraint("external_id", name="uq_test_sales_external_id"),
        sa.CheckConstraint("quantity BETWEEN 1 AND 99", name="ck_test_sales_quantity_range"),
        schema="marketplace",
    )
    op.create_index("test_sales_modified_idx", "test_sales", ["modified_at"], schema="marketplace")


def downgrade() -> None:
    # Marketplace orders cannot go back to a shop without channels: refuse before dropping.
    op.execute(
        "DO $$ BEGIN IF EXISTS (SELECT 1 FROM sales.orders WHERE channel <> 'shop') THEN "
        "RAISE EXCEPTION 'orders from a marketplace exist; remove them before downgrading'; "
        "END IF; END $$"
    )
    op.execute("DROP SCHEMA marketplace CASCADE")
    op.drop_constraint("ck_orders_cancel_reason", "orders", schema="sales", type_="check")
    op.create_check_constraint(
        "ck_orders_cancel_reason", "orders", _CANCEL_REASONS_BEFORE, schema="sales"
    )
    op.drop_index("orders_external_ref_idx", table_name="orders", schema="sales")
    op.drop_constraint("ck_orders_external_ref", "orders", schema="sales", type_="check")
    op.drop_constraint("ck_orders_channel", "orders", schema="sales", type_="check")
    op.drop_column("orders", "external_ref", schema="sales")
    op.drop_column("orders", "channel", schema="sales")
