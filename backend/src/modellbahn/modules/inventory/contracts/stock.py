"""Facade for other modules: free stock and how far an order is picked (sales), and the
pieces of variants a product being deleted takes along (catalog).

It runs SQL, so a domain layer must not import it (the pure-domain contract says so).
"""

from collections.abc import Collection
from dataclasses import dataclass
from typing import Final
from uuid import UUID

from sqlalchemy import Select, delete, func, select, update

from modellbahn.modules.inventory.contracts.availability import PickProgress
from modellbahn.modules.inventory.domain.model import AllocationStatus, UnitStatus
from modellbahn.modules.inventory.infrastructure.tables import (
    allocations,
    part_ledger,
    stock_ledger,
    units,
)
from modellbahn.platform.uow import UnitOfWork

__all__ = [
    "PickProgress",
    "UnitsOfVariants",
    "count_units_of_variants",
    "load_free_units",
    "load_pick_progress",
    "remove_unsold_units",
]

# Pieces that never left the shop: labelled, on a shelf or scrapped.
_UNSOLD: Final = (UnitStatus.LABELED, UnitStatus.IN_STOCK, UnitStatus.SCRAPPED)


@dataclass(frozen=True, slots=True)
class UnitsOfVariants:
    unsold: int
    """Labelled, on a shelf or scrapped, never assembled: they may go with their variant."""
    kept: int
    """Reserved, picked, shipped, or assembled from parts: they are history and stay."""


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


def _unsold_units(ids: list[UUID]) -> Select[tuple[UUID]]:
    assembled = select(part_ledger.c.unit_id).where(part_ledger.c.unit_id.is_not(None))
    return select(units.c.id).where(
        units.c.variant_id.in_(ids),
        units.c.status.in_(_UNSOLD),
        units.c.id.not_in(assembled),
    )


async def count_units_of_variants(
    uow: UnitOfWork, variant_ids: Collection[UUID]
) -> UnitsOfVariants:
    """How many pieces of the variants could go with them, and how many must stay."""
    ids = list(set(variant_ids))
    if not ids:
        return UnitsOfVariants(unsold=0, kept=0)
    total = (
        await uow.session.execute(select(func.count()).where(units.c.variant_id.in_(ids)))
    ).scalar_one()
    unsold = (
        await uow.session.execute(select(func.count()).select_from(_unsold_units(ids).subquery()))
    ).scalar_one()
    return UnitsOfVariants(unsold=int(unsold), kept=int(total) - int(unsold))


async def remove_unsold_units(uow: UnitOfWork, variant_ids: Collection[UUID]) -> int:
    """Delete the pieces of the variants that never left the shop, with their journal.

    For test models: the catalogue deletes a product only when no piece of it was sold.
    Pieces that must stay (see :class:`UnitsOfVariants`) are left as they are.
    """
    ids = list(set(variant_ids))
    if not ids:
        return 0
    doomed = [row[0] for row in await uow.session.execute(_unsold_units(ids))]
    if not doomed:
        return 0
    # An undo names the entry it reverses; both belong to the same piece and go together.
    await uow.session.execute(
        update(stock_ledger).where(stock_ledger.c.unit_id.in_(doomed)).values(reverses_id=None)
    )
    await uow.session.execute(delete(stock_ledger).where(stock_ledger.c.unit_id.in_(doomed)))
    await uow.session.execute(delete(units).where(units.c.id.in_(doomed)))
    return len(doomed)
