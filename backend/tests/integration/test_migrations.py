"""The hand-written migration: round trip, and agreement with the SQLAlchemy tables."""

import asyncio
import secrets
from collections.abc import Iterator
from typing import Any

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import Connection, text
from sqlalchemy.ext.asyncio import AsyncEngine

from modellbahn.modules.identity.infrastructure import tables as identity_tables
from modellbahn.platform import outbox
from modellbahn.platform.db import create_engine, metadata
from tests.support import create_database, downgrade, drop_database, migrate

SCHEMAS = ("platform", "identity")


@pytest.fixture
def scratch_database_url(postgres_server_url: str) -> Iterator[str]:
    name = f"modellbahn_migration_{secrets.token_hex(6)}"
    url = asyncio.run(create_database(postgres_server_url, name))
    try:
        yield url
    finally:
        asyncio.run(drop_database(postgres_server_url, name))


async def _tables(database_url: str) -> set[str]:
    engine = create_engine(database_url)
    try:
        async with engine.connect() as connection:
            rows = await connection.execute(
                text(
                    "SELECT table_schema || '.' || table_name FROM information_schema.tables "
                    "WHERE table_schema IN ('platform', 'identity')"
                )
            )
            return set(rows.scalars())
    finally:
        await engine.dispose()


def test_upgrade_downgrade_upgrade(scratch_database_url: str) -> None:
    expected = {
        "platform.outbox",
        "identity.accounts",
        "identity.sessions",
        "identity.account_tokens",
    }
    migrate(scratch_database_url)
    assert asyncio.run(_tables(scratch_database_url)) == expected
    downgrade(scratch_database_url)
    assert asyncio.run(_tables(scratch_database_url)) == set()
    migrate(scratch_database_url)
    assert asyncio.run(_tables(scratch_database_url)) == expected


def _include(name: str | None, type_: str, parent_names: Any) -> bool:
    if type_ == "schema":
        return name in SCHEMAS
    return True


def _differences(connection: Connection) -> list[Any]:
    context = MigrationContext.configure(
        connection, opts={"include_schemas": True, "include_name": _include}
    )
    return list(compare_metadata(context, metadata))


async def test_tables_match_the_migration(engine: AsyncEngine) -> None:
    # Both modules' tables are registered on the shared metadata.
    assert outbox.outbox_table.metadata is metadata
    assert identity_tables.accounts.metadata is metadata
    async with engine.connect() as connection:
        assert await connection.run_sync(_differences) == []


async def test_constraint_names_follow_the_convention(engine: AsyncEngine) -> None:
    async with engine.connect() as connection:
        rows = await connection.execute(
            text(
                "SELECT conname FROM pg_constraint c JOIN pg_namespace n ON n.oid = c.connamespace "
                "WHERE n.nspname IN ('platform', 'identity')"
            )
        )
        names = set(rows.scalars())
    assert {
        "pk_outbox",
        "ck_outbox_published_at",
        "uq_accounts_kind_email",
        "uq_accounts_id_kind",
        "ck_accounts_role_only_for_staff",
        "fk_sessions_account_id_kind_accounts",
        "uq_account_tokens_source_event_id",
        "fk_account_tokens_account_id_accounts",
    } <= names
