"""Imperative mapping of the sales domain classes onto their tables.

Order lines and payments belong to the order aggregate, cart lines to the cart; they are
loaded with their root (``selectin``: the async session cannot load lazily). Addresses
are value objects stored in columns of their owner (``composite``).
"""

from sqlalchemy import inspect
from sqlalchemy.orm import composite, relationship

from modellbahn.modules.sales.domain.model import (
    Cart,
    CartLine,
    CustomerAddress,
    Order,
    OrderLine,
    Payment,
    PostalAddress,
)
from modellbahn.modules.sales.infrastructure import tables
from modellbahn.platform.db import mapper_registry


def start_mappers() -> None:
    """Map the sales classes. Safe to call more than once."""
    if inspect(Order, raiseerr=False) is not None:
        return
    mapper_registry.map_imperatively(CartLine, tables.cart_lines)
    mapper_registry.map_imperatively(
        Cart,
        tables.carts,
        properties={
            "lines": relationship(
                CartLine,
                cascade="all, delete-orphan",
                passive_deletes=True,
                lazy="selectin",
                order_by=tables.cart_lines.c.added_at,
            )
        },
    )
    mapper_registry.map_imperatively(OrderLine, tables.order_lines)
    mapper_registry.map_imperatively(Payment, tables.payments)
    orders = tables.orders.c
    mapper_registry.map_imperatively(
        Order,
        tables.orders,
        # The column only exists for the foreign key on (id, kind); the database fills it.
        exclude_properties=["customer_kind"],
        properties={
            "shipping_address": composite(
                PostalAddress,
                orders.ship_recipient,
                orders.ship_street,
                orders.ship_postal_code,
                orders.ship_city,
                orders.ship_country,
            ),
            "lines": relationship(
                OrderLine,
                cascade="all, delete-orphan",
                passive_deletes=True,
                lazy="selectin",
                order_by=tables.order_lines.c.position,
            ),
            "payments": relationship(
                Payment,
                cascade="all, delete-orphan",
                passive_deletes=True,
                lazy="selectin",
                order_by=tables.payments.c.created_at,
            ),
        },
    )
    addresses = tables.customer_addresses.c
    mapper_registry.map_imperatively(
        CustomerAddress,
        tables.customer_addresses,
        exclude_properties=["account_kind"],
        properties={
            "address": composite(
                PostalAddress,
                addresses.recipient,
                addresses.street,
                addresses.postal_code,
                addresses.city,
                addresses.country_code,
            ),
        },
    )
