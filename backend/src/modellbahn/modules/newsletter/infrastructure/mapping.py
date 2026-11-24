"""Imperative mapping of the newsletter's domain classes onto their tables."""

from sqlalchemy import inspect

from modellbahn.modules.newsletter.domain.model import Delivery, Issue, Subscription
from modellbahn.modules.newsletter.infrastructure import tables
from modellbahn.platform.db import mapper_registry


def start_mappers() -> None:
    """Map the newsletter classes. Safe to call more than once."""
    if inspect(Subscription, raiseerr=False) is not None:
        return
    mapper_registry.map_imperatively(Subscription, tables.subscriptions)
    mapper_registry.map_imperatively(Issue, tables.issues)
    mapper_registry.map_imperatively(Delivery, tables.deliveries)
