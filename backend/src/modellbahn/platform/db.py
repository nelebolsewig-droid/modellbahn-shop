"""Database plumbing shared by all modules: metadata, mapper registry, engine, sessions."""

from enum import StrEnum
from typing import Any, Final

from sqlalchemy import MetaData, Text
from sqlalchemy.engine import Dialect, make_url
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import registry
from sqlalchemy.types import TypeDecorator

# Every constraint gets a predictable name. The hand-written migrations use exactly
# these names, so that errors can be matched on them and future migrations can
# refer to them.
NAMING_CONVENTION: Final[dict[str, str]] = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_N_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

metadata = MetaData(naming_convention=NAMING_CONVENTION)
"""The one :class:`MetaData` all module tables (in their own schemas) belong to."""

mapper_registry = registry(metadata=metadata)
"""Registry used by the modules to map their domain classes imperatively."""


class StrEnumType[E: StrEnum](TypeDecorator[E]):
    """Stores a :class:`~enum.StrEnum` as plain ``text``.

    The allowed values are enforced by a CHECK constraint in the migration, which
    keeps adding a value a one-line migration instead of an ``ALTER TYPE``.
    """

    impl = Text
    cache_ok = True

    def __init__(self, enum_class: type[E]) -> None:
        super().__init__()
        self.enum_class = enum_class

    def process_bind_param(self, value: E | str | None, dialect: Dialect) -> str | None:
        return None if value is None else self.enum_class(value).value

    def process_result_value(self, value: Any, dialect: Dialect) -> E | None:
        return None if value is None else self.enum_class(value)


def create_engine(database_url: str) -> AsyncEngine:
    """Create the async engine (asyncpg). Connections are opened lazily."""
    return create_async_engine(database_url, pool_pre_ping=True)


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Create the session factory used by the units of work.

    ``expire_on_commit`` is off so that aggregates stay readable after the unit of
    work has committed (e.g. to render the response).
    """
    return async_sessionmaker(engine, expire_on_commit=False)


def asyncpg_dsn(database_url: str) -> str:
    """Turn an SQLAlchemy URL (``postgresql+asyncpg://``) into a plain asyncpg DSN."""
    return make_url(database_url).set(drivername="postgresql").render_as_string(hide_password=False)
