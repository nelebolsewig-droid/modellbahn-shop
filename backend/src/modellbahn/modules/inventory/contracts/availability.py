"""The availability rule and the picking progress, for the sales module's use cases.

Plain Python like the domain it comes from: importing it keeps a layer free of SQL.
The facade that fills these from the database is :mod:`.stock`.
"""

from dataclasses import dataclass
from uuid import UUID

from modellbahn.modules.inventory.domain.availability import Availability, availability

__all__ = ["Availability", "PickProgress", "availability"]


@dataclass(frozen=True, slots=True)
class PickProgress:
    """How many pieces of an order the workshop owes, how many are picked, and which
    variants still wait for a piece (backordered: no unit to send yet)."""

    total: int
    picked: int
    waiting_variant_ids: tuple[UUID, ...] = ()
    """A variant once per piece still waiting for the workshop."""

    @property
    def is_shippable(self) -> bool:
        """Allocated, and every piece has a unit: reserved ones are picked on shipping."""
        return self.total > 0 and not self.waiting_variant_ids

    @property
    def is_allocated(self) -> bool:
        return self.total > 0

    @property
    def is_complete(self) -> bool:
        return self.total > 0 and self.picked == self.total
