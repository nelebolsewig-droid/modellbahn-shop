"""Read-only facade for the sales module: an order as a marketplace reported it.

It runs SQL, so a domain layer must not import it (the pure-domain contract says so).
"""

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

__all__ = ["ReceivedOrder", "ReceivedOrderLine", "load_received_order"]


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
