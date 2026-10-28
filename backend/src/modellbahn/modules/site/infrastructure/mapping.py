"""Imperative mapping of the site's domain classes onto their tables."""

from sqlalchemy import inspect

from modellbahn.modules.site.domain.model import Fair, Mailing, Subscription
from modellbahn.modules.site.infrastructure import tables
from modellbahn.platform.db import mapper_registry


def start_mappers() -> None:
    """Map the site classes. Safe to call more than once."""
    if inspect(Fair, raiseerr=False) is not None:
        return
    mapper_registry.map_imperatively(Fair, tables.fairs)
    mapper_registry.map_imperatively(Subscription, tables.subscriptions)
    mapper_registry.map_imperatively(Mailing, tables.mailings)
