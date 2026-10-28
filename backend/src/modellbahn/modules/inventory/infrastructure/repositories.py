"""SQLAlchemy implementations of the inventory repositories and unit of work.

Repositories only read and stage changes; committing is the unit of work's job.
"""

from collections.abc import Collection
from functools import partial
from uuid import UUID

from sqlalchemy import ColumnElement, Select, cast, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from modellbahn.modules.catalog.contracts.variants import (
    SaleVariant,
    load_product_variants,
    load_sale_variants,
    load_variant_by_gtin,
)
from modellbahn.modules.identity.contracts.accounts import load_display_names
from modellbahn.modules.inventory.application.ports import StockCount
from modellbahn.modules.inventory.domain.model import (
    Allocation,
    AllocationStatus,
    LedgerEntry,
    Location,
    Scan,
    Unit,
    UnitStatus,
)
from modellbahn.modules.inventory.infrastructure.mapping import start_mappers
from modellbahn.modules.inventory.infrastructure.tables import (
    allocations,
    locations,
    scans,
    stock_ledger,
    units,
)
from modellbahn.modules.sales.contracts.orders import (
    OrderSummary,
    load_order_numbers,
    load_order_summary,
)
from modellbahn.platform.db import Ltree
from modellbahn.platform.uow import UnitOfWork


def _locked[*Ts](statement: Select[*Ts], for_update: bool) -> Select[*Ts]:
    if not for_update:
        return statement
    # FOR NO KEY UPDATE: no use case changes a key, and journal entries referring to a
    # unit only take a key-share lock on it.
    return statement.with_for_update(key_share=True).execution_options(populate_existing=True)


def _unserved() -> ColumnElement[bool]:
    """Open allocations that no unit serves yet: the backorders."""
    return ~exists().where(units.c.allocation_id == allocations.c.id)


class SqlLocationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, location_id: UUID) -> Location | None:
        return await self._session.get(Location, location_id)

    async def get_by_code(self, code: str, *, for_update: bool = False) -> Location | None:
        statement = _locked(select(Location).where(locations.c.code == code), for_update)
        return (await self._session.execute(statement)).scalar_one_or_none()

    async def by_ids(self, location_ids: Collection[UUID]) -> dict[UUID, Location]:
        ids = list(set(location_ids))
        if not ids:
            return {}
        rows = await self._session.execute(select(Location).where(locations.c.id.in_(ids)))
        return {location.id: location for location in rows.scalars()}

    async def tree(self) -> list[Location]:
        statement = select(Location).order_by(locations.c.path)
        return list((await self._session.execute(statement)).scalars())

    async def subtree(self, location: Location) -> list[Location]:
        statement = (
            select(Location)
            .where(locations.c.path.op("<@")(cast(location.path, Ltree())))
            .order_by(locations.c.path)
        )
        return list((await self._session.execute(statement)).scalars())

    def add(self, location: Location) -> None:
        self._session.add(location)

    async def delete(self, location: Location) -> None:
        await self._session.delete(location)

    async def has_children(self, location_id: UUID) -> bool:
        statement = select(exists().where(locations.c.parent_id == location_id))
        return bool(await self._session.scalar(statement))

    async def in_journal(self, location_id: UUID) -> bool:
        statement = select(
            exists().where(
                or_(
                    stock_ledger.c.from_location_id == location_id,
                    stock_ledger.c.to_location_id == location_id,
                )
            )
        )
        return bool(await self._session.scalar(statement))

    async def unit_counts(self) -> dict[UUID, int]:
        statement = (
            select(units.c.location_id, func.count())
            .where(units.c.location_id.is_not(None))
            .group_by(units.c.location_id)
        )
        rows = await self._session.execute(statement)
        return {row[0]: int(row[1]) for row in rows}


class SqlUnitRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, unit_id: UUID, *, for_update: bool = False) -> Unit | None:
        statement = _locked(select(Unit).where(units.c.id == unit_id), for_update)
        return (await self._session.execute(statement)).scalar_one_or_none()

    async def get_by_code(self, code: str, *, for_update: bool = False) -> Unit | None:
        statement = _locked(select(Unit).where(units.c.code == code), for_update)
        return (await self._session.execute(statement)).scalar_one_or_none()

    async def existing_codes(self, codes: Collection[str]) -> set[str]:
        if not codes:
            return set()
        rows = await self._session.execute(select(units.c.code).where(units.c.code.in_(codes)))
        return set(rows.scalars())

    def add(self, unit: Unit) -> None:
        self._session.add(unit)

    async def in_locations(self, location_ids: Collection[UUID]) -> list[Unit]:
        ids = list(set(location_ids))
        if not ids:
            return []
        statement = (
            select(Unit)
            .where(units.c.location_id.in_(ids))
            .order_by(units.c.created_at, units.c.id)
        )
        return list((await self._session.execute(statement)).scalars())

    async def oldest_labeled(self, variant_id: UUID) -> Unit | None:
        statement = (
            select(Unit)
            .where(units.c.variant_id == variant_id, units.c.status == UnitStatus.LABELED)
            .order_by(units.c.created_at, units.c.id)
            .limit(1)
            .with_for_update(key_share=True, skip_locked=True)
            .execution_options(populate_existing=True)
        )
        return (await self._session.execute(statement)).scalar_one_or_none()

    async def oldest_free(self, variant_id: UUID, *, limit: int) -> list[Unit]:
        statement = (
            select(Unit)
            .where(units.c.variant_id == variant_id, units.c.status == UnitStatus.IN_STOCK)
            .order_by(units.c.created_at, units.c.id)
            .limit(limit)
            # Two orders allocating at once take different units instead of waiting.
            .with_for_update(key_share=True, skip_locked=True)
            .execution_options(populate_existing=True)
        )
        return list((await self._session.execute(statement)).scalars())

    async def serving(
        self, allocation_ids: Collection[UUID], *, for_update: bool = False
    ) -> dict[UUID, Unit]:
        ids = list(set(allocation_ids))
        if not ids:
            return {}
        statement = _locked(select(Unit).where(units.c.allocation_id.in_(ids)), for_update)
        found = (await self._session.execute(statement)).scalars()
        return {unit.allocation_id: unit for unit in found if unit.allocation_id is not None}

    async def counts(self, variant_ids: Collection[UUID] | None = None) -> list[StockCount]:
        statement = select(units.c.variant_id, units.c.status, func.count()).group_by(
            units.c.variant_id, units.c.status
        )
        if variant_ids is not None:
            ids = list(set(variant_ids))
            if not ids:
                return []
            statement = statement.where(units.c.variant_id.in_(ids))
        rows = await self._session.execute(statement)
        return [
            StockCount(variant_id=row[0], status=UnitStatus(row[1]), count=int(row[2]))
            for row in rows
        ]


class SqlAllocationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, allocation_id: UUID) -> Allocation | None:
        return await self._session.get(Allocation, allocation_id)

    async def by_ids(self, allocation_ids: Collection[UUID]) -> dict[UUID, Allocation]:
        ids = list(set(allocation_ids))
        if not ids:
            return {}
        rows = await self._session.execute(select(Allocation).where(allocations.c.id.in_(ids)))
        return {allocation.id: allocation for allocation in rows.scalars()}

    async def for_order(self, order_id: UUID, *, for_update: bool = False) -> list[Allocation]:
        statement = _locked(
            select(Allocation).where(allocations.c.order_id == order_id).order_by(allocations.c.id),
            for_update,
        )
        return list((await self._session.execute(statement)).scalars())

    async def oldest_backorder(self, variant_id: UUID) -> Allocation | None:
        statement = (
            select(Allocation)
            .where(
                allocations.c.variant_id == variant_id,
                allocations.c.status == AllocationStatus.OPEN,
                _unserved(),
            )
            .order_by(allocations.c.created_at, allocations.c.id)
            .limit(1)
            .with_for_update(key_share=True, skip_locked=True)
        )
        return (await self._session.execute(statement)).scalar_one_or_none()

    async def backorder_counts(
        self, variant_ids: Collection[UUID] | None = None
    ) -> dict[UUID, int]:
        statement = (
            select(allocations.c.variant_id, func.count())
            .where(allocations.c.status == AllocationStatus.OPEN, _unserved())
            .group_by(allocations.c.variant_id)
        )
        if variant_ids is not None:
            statement = statement.where(allocations.c.variant_id.in_(list(set(variant_ids))))
        rows = await self._session.execute(statement)
        return {row[0]: int(row[1]) for row in rows}

    def add(self, allocation: Allocation) -> None:
        self._session.add(allocation)


class SqlLedgerRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def add(self, entry: LedgerEntry) -> None:
        self._session.add(entry)

    async def for_unit(self, unit_id: UUID) -> list[LedgerEntry]:
        statement = (
            select(LedgerEntry).where(stock_ledger.c.unit_id == unit_id).order_by(stock_ledger.c.id)
        )
        return list((await self._session.execute(statement)).scalars())

    async def for_scan(self, scan_id: UUID) -> list[LedgerEntry]:
        statement = (
            select(LedgerEntry).where(stock_ledger.c.scan_id == scan_id).order_by(stock_ledger.c.id)
        )
        return list((await self._session.execute(statement)).scalars())


class SqlScanRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, scan_id: UUID, *, for_update: bool = False) -> Scan | None:
        statement = _locked(select(Scan).where(scans.c.id == scan_id), for_update)
        return (await self._session.execute(statement)).scalar_one_or_none()

    def add(self, scan: Scan) -> None:
        self._session.add(scan)


class SqlCatalog:
    """The catalogue's variant facade, inside this unit of work's transaction."""

    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    async def variants(self, variant_ids: Collection[UUID]) -> dict[UUID, SaleVariant]:
        return await load_sale_variants(self._uow, variant_ids)

    async def variant_by_gtin(self, gtin: str) -> SaleVariant | None:
        return await load_variant_by_gtin(self._uow, gtin)

    async def product_variants(self, slug: str) -> list[SaleVariant]:
        return await load_product_variants(self._uow, slug)


class SqlOrders:
    """The sales module's order facade, inside this unit of work's transaction."""

    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    async def summary(self, order_id: UUID) -> OrderSummary | None:
        return await load_order_summary(self._uow, order_id)

    async def numbers(self, order_ids: Collection[UUID]) -> dict[UUID, str]:
        return await load_order_numbers(self._uow, order_ids)


class SqlStaff:
    """The identity module's account facade, inside this unit of work's transaction."""

    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    async def names(self, account_ids: Collection[UUID]) -> dict[UUID, str]:
        return await load_display_names(self._uow, account_ids)


class SqlInventoryUnitOfWork(UnitOfWork):
    """Unit of work with the inventory repositories attached."""

    locations: SqlLocationRepository
    units: SqlUnitRepository
    allocations: SqlAllocationRepository
    ledger: SqlLedgerRepository
    scans: SqlScanRepository
    catalog: SqlCatalog
    orders: SqlOrders
    staff: SqlStaff

    def _attach(self, session: AsyncSession) -> None:
        start_mappers()
        self.locations = SqlLocationRepository(session)
        self.units = SqlUnitRepository(session)
        self.allocations = SqlAllocationRepository(session)
        self.ledger = SqlLedgerRepository(session)
        self.scans = SqlScanRepository(session)
        self.catalog = SqlCatalog(self)
        self.orders = SqlOrders(self)
        self.staff = SqlStaff(self)


def inventory_uow_factory(
    session_factory: async_sessionmaker[AsyncSession],
) -> partial[SqlInventoryUnitOfWork]:
    """The factory the inventory services get: a fresh unit of work per call."""
    return partial(SqlInventoryUnitOfWork, session_factory)
