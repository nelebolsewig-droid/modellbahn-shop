"""Read-only facade for orders, for the inventory module (allocation and picking).

It runs SQL, so a domain layer must not import it (the pure-domain contract says so).
"""

from collections.abc import Collection
from dataclasses import dataclass
from datetime import datetime
from typing import Final
from uuid import UUID

from sqlalchemy import select

from modellbahn.modules.sales.domain.model import OrderStatus
from modellbahn.modules.sales.infrastructure.tables import order_lines, orders
from modellbahn.platform.uow import UnitOfWork

__all__ = [
    "ORDER_REFERENCE",
    "OrderLineSummary",
    "OrderStatus",
    "OrderSummary",
    "load_order_numbers",
    "load_order_summary",
]

ORDER_REFERENCE: Final = "sales.orders.id"
"""Target for another module's foreign key to an order (``RESTRICT``; orders are never
deleted). Importing it also puts the sales tables on the shared metadata, which
SQLAlchemy needs to resolve the key."""


@dataclass(frozen=True, slots=True)
class OrderLineSummary:
    """A line as the customer ordered it (frozen at checkout)."""

    id: UUID
    position: int
    variant_id: UUID
    sku: str
    title: str
    quantity: int


@dataclass(frozen=True, slots=True)
class OrderSummary:
    """What the workshop needs to know about an order to allocate, pick and pack it."""

    id: UUID
    number: str
    status: OrderStatus
    paid_at: datetime | None
    ship_recipient: str
    lines: list[OrderLineSummary]


async def load_order_summary(uow: UnitOfWork, order_id: UUID) -> OrderSummary | None:
    """The order with its lines, read inside the caller's unit of work."""
    order = (
        await uow.session.execute(
            select(
                orders.c.id,
                orders.c.number,
                orders.c.status,
                orders.c.paid_at,
                orders.c.ship_recipient,
            ).where(orders.c.id == order_id)
        )
    ).one_or_none()
    if order is None:
        return None
    lines = await uow.session.execute(
        select(
            order_lines.c.id,
            order_lines.c.position,
            order_lines.c.variant_id,
            order_lines.c.sku,
            order_lines.c.title,
            order_lines.c.quantity,
        )
        .where(order_lines.c.order_id == order_id)
        .order_by(order_lines.c.position)
    )
    return OrderSummary(
        id=order.id,
        number=order.number,
        status=order.status,
        paid_at=order.paid_at,
        ship_recipient=order.ship_recipient,
        lines=[
            OrderLineSummary(
                id=line.id,
                position=line.position,
                variant_id=line.variant_id,
                sku=line.sku,
                title=line.title,
                quantity=line.quantity,
            )
            for line in lines
        ],
    )


async def load_order_numbers(uow: UnitOfWork, order_ids: Collection[UUID]) -> dict[UUID, str]:
    """The readable numbers (``MB-2026-00042``) of the orders among ``order_ids``."""
    ids = list(set(order_ids))
    if not ids:
        return {}
    rows = await uow.session.execute(
        select(orders.c.id, orders.c.number).where(orders.c.id.in_(ids))
    )
    return {row.id: row.number for row in rows}
