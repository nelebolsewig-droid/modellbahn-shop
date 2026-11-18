"""Facade for planning (ADR 0034): which paid pieces wait for the workshop, and which
printed parts are already there to make them from.

It runs SQL, so a domain layer must not import it (the pure-domain contract says so).
"""

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import exists, func, select

from modellbahn.modules.inventory.domain.model import AllocationStatus
from modellbahn.modules.inventory.infrastructure.tables import (
    allocations,
    part_receipts,
    part_stock,
    units,
)
from modellbahn.platform.uow import UnitOfWork

__all__ = ["WaitingPiece", "load_part_supply", "load_waiting_pieces"]


@dataclass(frozen=True, slots=True)
class WaitingPiece:
    """One paid piece without a unit: the workshop has to make it."""

    order_id: UUID
    variant_id: UUID


async def load_waiting_pieces(uow: UnitOfWork) -> list[WaitingPiece]:
    """Every open allocation no unit serves yet, the oldest first."""
    rows = await uow.session.execute(
        select(allocations.c.order_id, allocations.c.variant_id)
        .where(
            allocations.c.status == AllocationStatus.OPEN,
            ~exists().where(units.c.allocation_id == allocations.c.id),
        )
        .order_by(allocations.c.created_at, allocations.c.id)
    )
    return [WaitingPiece(order_id=row.order_id, variant_id=row.variant_id) for row in rows]


async def load_part_supply(uow: UnitOfWork) -> dict[UUID, int]:
    """Printed parts per part that can go into a kit: in the boxes, and still in receiving."""
    supply: dict[UUID, int] = {}
    stored = await uow.session.execute(
        select(part_stock.c.part_id, func.sum(part_stock.c.quantity))
        .where(part_stock.c.quantity > 0)
        .group_by(part_stock.c.part_id)
    )
    for part_id, quantity in stored:
        supply[part_id] = supply.get(part_id, 0) + int(quantity)
    left = part_receipts.c.quantity - part_receipts.c.stored - part_receipts.c.written_off
    arriving = await uow.session.execute(
        select(part_receipts.c.part_id, func.sum(left))
        .where(left > 0)
        .group_by(part_receipts.c.part_id)
    )
    for part_id, quantity in arriving:
        supply[part_id] = supply.get(part_id, 0) + int(quantity)
    return supply
