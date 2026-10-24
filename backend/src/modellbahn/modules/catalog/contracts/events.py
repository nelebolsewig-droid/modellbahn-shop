"""Catalogue events, for other modules to react to.

Plain Python like the domain it comes from: importing it keeps a domain layer pure.
"""

from modellbahn.modules.catalog.domain.events import (
    ProductArchived,
    ProductPublished,
    ProductUpdated,
)

__all__ = ["ProductArchived", "ProductPublished", "ProductUpdated"]
