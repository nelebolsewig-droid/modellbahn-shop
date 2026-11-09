"""Imperative mapping of the AI module's domain classes onto their tables."""

from sqlalchemy import inspect

from modellbahn.modules.ai.domain.model import AiRun
from modellbahn.modules.ai.infrastructure import tables
from modellbahn.platform.db import mapper_registry


def start_mappers() -> None:
    """Map the AI classes. Safe to call more than once."""
    if inspect(AiRun, raiseerr=False) is not None:
        return
    mapper_registry.map_imperatively(AiRun, tables.runs)
