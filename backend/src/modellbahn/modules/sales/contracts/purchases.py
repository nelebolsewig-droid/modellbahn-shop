"""Read-only facade for the newsletter: what a customer account has bought.

It runs SQL, so a domain layer must not import it (the pure-domain contract says so).
"""

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select

from modellbahn.modules.sales.domain.model import OrderStatus
from modellbahn.modules.sales.infrastructure.tables import order_lines, orders
from modellbahn.platform.uow import UnitOfWork

__all__ = ["Purchase", "load_purchases"]


@dataclass(frozen=True, slots=True)
class Purchase:
    """A model bought in a scale (paid or shipped, not cancelled)."""

    product_slug: str
    scale_code: str


async def load_purchases(uow: UnitOfWork, account_id: UUID) -> frozenset[Purchase]:
    """The models the customer account bought, each once."""
    rows = await uow.session.execute(
        select(order_lines.c.product_slug, order_lines.c.scale_code)
        .join(orders, orders.c.id == order_lines.c.order_id)
        .where(
            orders.c.customer_account_id == account_id,
            orders.c.status.in_([OrderStatus.PAID, OrderStatus.SHIPPED]),
        )
        .distinct()
    )
    return frozenset(Purchase(row.product_slug, row.scale_code) for row in rows)
