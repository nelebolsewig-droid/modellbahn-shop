"""Read-only facade: an order as a marketplace reported it (for sales), and the orders
that still involve a variant (for the catalogue, before it deletes a product).

It runs SQL, so a domain layer must not import it (the pure-domain contract says so).
"""

from collections.abc import Collection
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import select

from modellbahn.modules.marketplace.domain.model import MarketplaceOrderStatus
from modellbahn.modules.marketplace.infrastructure.tables import (
    marketplace_order_lines,
    marketplace_orders,
)
from modellbahn.platform.uow import UnitOfWork

__all__ = [
    "ReceivedOrder",
    "ReceivedOrderLine",
    "load_received_order",
    "load_received_order_refs",
]


@dataclass(frozen=True, slots=True)
class ReceivedOrderLine:
    variant_id: UUID
    sku: str
    quantity: int
    unit_price_cents: int


@dataclass(frozen=True, slots=True)
class ReceivedOrder:
    """A paid marketplace order, ready to become one of the shop's orders."""

    order_id: UUID
    """The id the shop's order gets."""
    channel: str
    external_id: str
    email: str
    recipient: str
    street: str
    postal_code: str
    city: str
    country_code: str
    shipping_cents: int
    paid_at: datetime
    cancelled: bool
    lines: list[ReceivedOrderLine]


async def load_received_order(uow: UnitOfWork, marketplace_order_id: UUID) -> ReceivedOrder | None:
    """The order with its lines, if it was received (rejected orders never get here)."""
    order = (
        await uow.session.execute(
            select(marketplace_orders).where(marketplace_orders.c.id == marketplace_order_id)
        )
    ).one_or_none()
    if order is None or order.status == MarketplaceOrderStatus.REJECTED:
        return None
    lines = await uow.session.execute(
        select(
            marketplace_order_lines.c.variant_id,
            marketplace_order_lines.c.sku,
            marketplace_order_lines.c.quantity,
            marketplace_order_lines.c.unit_price_cents,
        )
        .where(marketplace_order_lines.c.marketplace_order_id == marketplace_order_id)
        .order_by(marketplace_order_lines.c.position)
    )
    return ReceivedOrder(
        order_id=order.order_id,
        channel=order.channel,
        external_id=order.external_id,
        email=order.email,
        recipient=order.recipient,
        street=order.street,
        postal_code=order.postal_code,
        city=order.city,
        country_code=order.country_code,
        shipping_cents=order.shipping_cents,
        paid_at=order.paid_at,
        cancelled=order.status == MarketplaceOrderStatus.CANCELLED,
        lines=[
            ReceivedOrderLine(
                variant_id=line.variant_id,
                sku=line.sku,
                quantity=line.quantity,
                unit_price_cents=line.unit_price_cents,
            )
            for line in lines
            if line.variant_id is not None
        ],
    )


async def load_received_order_refs(
    uow: UnitOfWork, variant_ids: Collection[UUID]
) -> dict[UUID, str]:
    """Received orders (neither shipped nor cancelled) with one of the variants.

    By the id the shop's order gets (or got), with the marketplace's own order number. One
    the shop has not made its own order of yet would be lost if the variant went away.
    """
    ids = list(set(variant_ids))
    if not ids:
        return {}
    rows = await uow.session.execute(
        select(marketplace_orders.c.order_id, marketplace_orders.c.external_id)
        .distinct()
        .join(
            marketplace_order_lines,
            marketplace_order_lines.c.marketplace_order_id == marketplace_orders.c.id,
        )
        .where(
            marketplace_order_lines.c.variant_id.in_(ids),
            marketplace_orders.c.status == MarketplaceOrderStatus.RECEIVED,
        )
    )
    return {row[0]: str(row[1]) for row in rows}
