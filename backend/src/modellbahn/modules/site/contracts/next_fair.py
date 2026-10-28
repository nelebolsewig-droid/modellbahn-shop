"""The next fair, as other modules may mention it (pure: no database, no framework)."""

from dataclasses import dataclass
from datetime import date

from modellbahn.modules.site.domain.dates import date_range


@dataclass(frozen=True, slots=True)
class NextFair:
    name: str
    city: str
    venue: str
    booth: str
    starts_on: date
    ends_on: date

    @property
    def when(self) -> str:
        """The dates in German, e.g. ``7. November 2026``."""
        return date_range(self.starts_on, self.ends_on)
