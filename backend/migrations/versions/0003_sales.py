"""Sales: carts, orders with lines and payments, customer address books.

Written by hand like 0001 and 0002. Constraint names follow the naming convention of
``modellbahn.platform.db``. Cart and order lines name catalogue variants without a
foreign key (a variant is not an aggregate root); orders and addresses refer to
customer accounts by ``(id, kind)``.

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CUSTOMER = sa.text("'customer'")
_EMPTY = sa.text("''")


def upgrade() -> None:
    op.execute("CREATE SCHEMA sales")
    op.execute("CREATE SEQUENCE sales.order_number_seq")
    _create_carts()
    _create_orders()
    _create_addresses()


def _create_carts() -> None:
    op.create_table(
        "carts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_carts"),
        sa.CheckConstraint("expires_at > updated_at", name="ck_carts_expires_after_update"),
        schema="sales",
    )
    op.create_index("carts_expires_idx", "carts", ["expires_at"], schema="sales")

    op.create_table(
        "cart_lines",
        sa.Column("cart_id", sa.Uuid(), nullable=False),
        # A catalogue variant; no foreign key, the cart checks it when it is read.
        sa.Column("variant_id", sa.Uuid(), nullable=False),
        sa.Column("quantity", sa.SmallInteger(), nullable=False),
        sa.Column("added_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("cart_id", "variant_id", name="pk_cart_lines"),
        sa.CheckConstraint("quantity BETWEEN 1 AND 99", name="ck_cart_lines_quantity_range"),
        sa.ForeignKeyConstraint(
            ["cart_id"], ["sales.carts.id"], name="fk_cart_lines_cart_id_carts", ondelete="CASCADE"
        ),
        schema="sales",
    )


def _create_orders() -> None:
    op.create_table(
        "orders",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("number", sa.Text(), nullable=False),
        sa.Column("public_token", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("customer_account_id", sa.Uuid(), nullable=True),
        sa.Column("customer_kind", sa.Text(), server_default=_CUSTOMER, nullable=False),
        sa.Column("email", postgresql.CITEXT(), nullable=False),
        sa.Column("ship_recipient", sa.Text(), nullable=False),
        sa.Column("ship_street", sa.Text(), nullable=False),
        sa.Column("ship_postal_code", sa.Text(), nullable=False),
        sa.Column("ship_city", sa.Text(), nullable=False),
        sa.Column("ship_country", sa.CHAR(2), nullable=False),
        sa.Column("subtotal_cents", sa.Integer(), nullable=False),
        sa.Column("shipping_cents", sa.Integer(), nullable=False),
        sa.Column("total_cents", sa.Integer(), nullable=False),
        sa.Column("tax_cents", sa.Integer(), nullable=False),
        sa.Column("checkout_key", sa.Uuid(), nullable=False),
        sa.Column("checkout_fingerprint", sa.CHAR(64), nullable=False),
        sa.Column("placed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("shipped_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancel_reason", sa.Text(), nullable=True),
        sa.Column("cancel_note", sa.Text(), server_default=_EMPTY, nullable=False),
        sa.Column("carrier", sa.Text(), server_default=_EMPTY, nullable=False),
        sa.Column("tracking_number", sa.Text(), server_default=_EMPTY, nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_orders"),
        sa.UniqueConstraint("number", name="uq_orders_number"),
        sa.UniqueConstraint("public_token", name="uq_orders_public_token"),
        sa.UniqueConstraint("checkout_key", name="uq_orders_checkout_key"),
        sa.CheckConstraint(
            "status IN ('pending_payment', 'paid', 'shipped', 'cancelled')",
            name="ck_orders_status",
        ),
        sa.CheckConstraint("number ~ '^MB-[0-9]{4}-[0-9]{5,}$'", name="ck_orders_number_format"),
        sa.CheckConstraint("customer_kind = 'customer'", name="ck_orders_customer_kind"),
        sa.CheckConstraint("ship_country ~ '^[A-Z]{2}$'", name="ck_orders_ship_country_format"),
        sa.CheckConstraint(
            "subtotal_cents >= 0 AND shipping_cents >= 0 AND tax_cents >= 0",
            name="ck_orders_amounts_non_negative",
        ),
        sa.CheckConstraint(
            "total_cents = subtotal_cents + shipping_cents", name="ck_orders_total_is_sum"
        ),
        sa.CheckConstraint("tax_cents <= total_cents", name="ck_orders_tax_within_total"),
        sa.CheckConstraint(
            "checkout_fingerprint ~ '^[0-9a-f]{64}$'", name="ck_orders_checkout_fingerprint_format"
        ),
        sa.CheckConstraint(
            "status NOT IN ('paid', 'shipped') OR paid_at IS NOT NULL",
            name="ck_orders_paid_has_time",
        ),
        sa.CheckConstraint(
            "(status = 'shipped') = (shipped_at IS NOT NULL)", name="ck_orders_shipped_at"
        ),
        sa.CheckConstraint(
            "(status = 'cancelled') = (cancelled_at IS NOT NULL AND cancel_reason IS NOT NULL)",
            name="ck_orders_cancelled_at",
        ),
        sa.CheckConstraint(
            "cancel_reason IS NULL OR cancel_reason IN ('payment_timeout', 'by_shop')",
            name="ck_orders_cancel_reason",
        ),
        # Across modules: customer accounts only, and never cascading (accounts are
        # anonymised, not deleted; orders stay for the retention periods).
        sa.ForeignKeyConstraint(
            ["customer_account_id", "customer_kind"],
            ["identity.accounts.id", "identity.accounts.kind"],
            name="fk_orders_customer_account_id_customer_kind_accounts",
            ondelete="RESTRICT",
        ),
        schema="sales",
    )
    op.create_index(
        "orders_customer_idx",
        "orders",
        ["customer_account_id", "placed_at"],
        schema="sales",
        postgresql_where=sa.text("customer_account_id IS NOT NULL"),
    )
    op.create_index(
        "orders_guest_email_idx",
        "orders",
        ["email"],
        schema="sales",
        postgresql_where=sa.text("customer_account_id IS NULL"),
    )
    op.create_index("orders_placed_idx", "orders", ["placed_at", "id"], schema="sales")
    op.create_index(
        "orders_pending_idx",
        "orders",
        ["placed_at"],
        schema="sales",
        postgresql_where=sa.text("status = 'pending_payment'"),
    )

    op.create_table(
        "order_lines",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("order_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.SmallInteger(), nullable=False),
        # Frozen copy of the variant at checkout; no foreign key into the catalogue.
        sa.Column("variant_id", sa.Uuid(), nullable=False),
        sa.Column("product_slug", sa.Text(), nullable=False),
        sa.Column("sku", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("scale_code", sa.Text(), nullable=False),
        sa.Column("finish_code", sa.Text(), nullable=False),
        sa.Column("unit_price_cents", sa.Integer(), nullable=False),
        sa.Column("quantity", sa.SmallInteger(), nullable=False),
        sa.Column("line_total_cents", sa.Integer(), nullable=False),
        sa.Column("image_asset_id", sa.Uuid(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_order_lines"),
        sa.CheckConstraint("quantity BETWEEN 1 AND 99", name="ck_order_lines_quantity_range"),
        sa.CheckConstraint("unit_price_cents >= 0", name="ck_order_lines_price_non_negative"),
        sa.CheckConstraint(
            "line_total_cents = unit_price_cents * quantity", name="ck_order_lines_line_total"
        ),
        sa.CheckConstraint("position >= 0", name="ck_order_lines_position_non_negative"),
        sa.ForeignKeyConstraint(
            ["order_id"],
            ["sales.orders.id"],
            name="fk_order_lines_order_id_orders",
            ondelete="CASCADE",
        ),
        schema="sales",
    )
    op.create_index(
        "order_lines_order_idx",
        "order_lines",
        ["order_id", "position"],
        unique=True,
        schema="sales",
    )

    op.create_table(
        "payments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("order_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("provider_ref", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("amount_cents", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", sa.Uuid(), nullable=False),
        sa.Column("request_fingerprint", sa.CHAR(64), nullable=False),
        sa.Column("failure_code", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_payments"),
        sa.UniqueConstraint("idempotency_key", name="uq_payments_idempotency_key"),
        sa.CheckConstraint(
            "status IN ('captured', 'failed', 'refunded')", name="ck_payments_status"
        ),
        sa.CheckConstraint("amount_cents >= 0", name="ck_payments_amount_non_negative"),
        sa.CheckConstraint(
            "request_fingerprint ~ '^[0-9a-f]{64}$'", name="ck_payments_request_fingerprint_format"
        ),
        sa.CheckConstraint(
            "(status = 'failed') = (failure_code IS NOT NULL)", name="ck_payments_failure_code"
        ),
        sa.ForeignKeyConstraint(
            ["order_id"],
            ["sales.orders.id"],
            name="fk_payments_order_id_orders",
            ondelete="CASCADE",
        ),
        schema="sales",
    )
    op.create_index(
        "payments_provider_ref_idx",
        "payments",
        ["provider", "provider_ref"],
        unique=True,
        schema="sales",
    )
    op.create_index("payments_order_idx", "payments", ["order_id"], schema="sales")


def _create_addresses() -> None:
    op.create_table(
        "customer_addresses",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("account_kind", sa.Text(), server_default=_CUSTOMER, nullable=False),
        sa.Column("label", sa.Text(), server_default=_EMPTY, nullable=False),
        sa.Column("recipient", sa.Text(), nullable=False),
        sa.Column("street", sa.Text(), nullable=False),
        sa.Column("postal_code", sa.Text(), nullable=False),
        sa.Column("city", sa.Text(), nullable=False),
        sa.Column("country_code", sa.CHAR(2), nullable=False),
        sa.Column("is_default", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_customer_addresses"),
        sa.CheckConstraint("account_kind = 'customer'", name="ck_customer_addresses_account_kind"),
        sa.CheckConstraint(
            "country_code ~ '^[A-Z]{2}$'", name="ck_customer_addresses_country_code_format"
        ),
        sa.ForeignKeyConstraint(
            ["account_id", "account_kind"],
            ["identity.accounts.id", "identity.accounts.kind"],
            name="fk_customer_addresses_account_id_account_kind_accounts",
            ondelete="RESTRICT",
        ),
        schema="sales",
    )
    # At most one default per book, checked at commit: switching it is a single step.
    op.execute(
        "ALTER TABLE sales.customer_addresses ADD CONSTRAINT ex_customer_addresses_one_default "
        "EXCLUDE USING btree (account_id WITH =) WHERE (is_default) DEFERRABLE INITIALLY DEFERRED"
    )
    op.create_index(
        "customer_addresses_account_idx", "customer_addresses", ["account_id"], schema="sales"
    )


def downgrade() -> None:
    op.drop_table("customer_addresses", schema="sales")
    op.drop_table("payments", schema="sales")
    op.drop_table("order_lines", schema="sales")
    op.drop_table("orders", schema="sales")
    op.drop_table("cart_lines", schema="sales")
    op.drop_table("carts", schema="sales")
    op.execute("DROP SEQUENCE sales.order_number_seq")
    op.execute("DROP SCHEMA sales")
