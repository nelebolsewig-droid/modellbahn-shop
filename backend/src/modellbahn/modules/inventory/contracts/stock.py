"""Read-only facade for the sales module: free stock and how far an order is picked.

It runs SQL, so a domain layer must not import it (the pure-domain contract says so).
"""

from collections.abc import Collection
from uuid import UUID

from sqlalchemy import func, select

from modellbahn.modules.inventory.contracts.availability import PickProgress
from modellbahn.modules.inventory.domain.model import AllocationStatus, UnitStatus
from modellbahn.modules.inventory.infrastructure.tables import allocations, units
from modellbahn.platform.uow import UnitOfWork

__all__ = ["PickProgress", "load_free_units", "load_pick_progress"]


async def load_free_units(uow: UnitOfWork, variant_ids: Collection[UUID]) -> dict[UUID, int]:
    """Units on the shelves that nobody has been promised, per variant (missing means 0)."""
    ids = list(set(variant_ids))
    if not ids:
        return {}
    rows = await uow.session.execute(
        select(units.c.variant_id, func.count())
        .where(units.c.variant_id.in_(ids), units.c.status == UnitStatus.IN_STOCK)
        .group_by(units.c.variant_id)
    )
    return {row[0]: int(row[1]) for row in rows}


async def load_pick_progress(uow: UnitOfWork, order_id: UUID) -> PickProgress:
    """The order's open pieces and how many of them are picked (0 of 0 if not allocated)."""
    row = (
        await uow.session.execute(
            select(
                func.count(allocations.c.id),
                func.count(units.c.id).filter(units.c.status == UnitStatus.PICKED),
            )
            .select_from(allocations)
            .outerjoin(units, units.c.allocation_id == allocations.c.id)
            .where(
                allocations.c.order_id == order_id,
                allocations.c.status == AllocationStatus.OPEN,
            )
        )
    ).one()
    return PickProgress(total=int(row[0]), picked=int(row[1]))
