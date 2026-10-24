"""Imperative mapping of the identity domain classes onto their tables.

The domain dataclasses stay free of SQLAlchemy; the ORM instruments them here, once
per process. Aggregates refer to each other by id only, so there are no relationships.
"""

from sqlalchemy import inspect

from modellbahn.modules.identity.domain.model import Account, AccountToken, LoginSession
from modellbahn.modules.identity.infrastructure import tables
from modellbahn.platform.db import mapper_registry


def start_mappers() -> None:
    """Map the identity classes. Safe to call more than once."""
    if inspect(Account, raiseerr=False) is not None:
        return
    mapper_registry.map_imperatively(
        Account,
        tables.accounts,
        # Concurrent writers of the same account fail instead of overwriting each other.
        version_id_col=tables.accounts.c.version,
    )
    mapper_registry.map_imperatively(LoginSession, tables.sessions)
    mapper_registry.map_imperatively(AccountToken, tables.account_tokens)
