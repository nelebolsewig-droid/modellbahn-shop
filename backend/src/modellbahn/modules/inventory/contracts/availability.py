"""The availability rule and the picking progress, for the sales module's use cases.

Plain Python like the domain it comes from: importing it keeps a layer free of SQL.
The facade that fills these from the database is :mod:`.stock`.
"""

from dataclasses import dataclass

from modellbahn.modules.inventory.domain.availability import Availability, availability

__all__ = ["Availability", "PickProgress", "availability"]


@dataclass(frozen=True, slots=True)
class PickProgress:
    """How many pieces of an order the workshop owes, and how many are picked."""

    total: int
    picked: int

    @property
    def is_allocated(self) -> bool:
        return self.total > 0

    @property
    def is_complete(self) -> bool:
        return self.total > 0 and self.picked == self.total
