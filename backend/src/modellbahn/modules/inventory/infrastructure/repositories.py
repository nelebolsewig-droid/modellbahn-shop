"""SQLAlchemy implementations of the inventory repositories and unit of work.

Repositories only read and stage changes; committing is the unit of work's job.
"""

from collections.abc import Collection
from datetime import datetime
from functools import partial
from uuid import UUID

from sqlalchemy import ColumnElement, Select, cast, exists, func, or_, select
from sqlalchemy.dialects.postgresql import insert
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
from modellbahn.modules.inventory.domain.parts import PartLedgerEntry, PartReceipt, PartStock
from modellbahn.modules.inventory.infrastructure.mapping import start_mappers
from modellbahn.modules.inventory.infrastructure.tables import (
    allocations,
    locations,
    part_ledger,
    part_receipts,
    part_stock,
    scans,
    stock_ledger,
    units,
)
from modellbahn.modules.manufacturing.contracts.parts import (
    KitPart,
    PartInfo,
    PrintJobInfo,
    PrintJobYield,
    load_bill_of_materials,
    load_part_by_number,
    load_parts,
    load_print_job_yield,
    load_print_jobs,
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


class SqlPartStockRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def lock(self, part_id: UUID, location_id: UUID, *, now: datetime) -> PartStock:
        # Two receipts into the same new box: one inserts the row, both then lock it.
        await self._session.execute(
            insert(part_stock)
            .values(part_id=part_id, location_id=location_id, quantity=0, updated_at=now)
            .on_conflict_do_nothing()
        )
        statement = _locked(
            select(PartStock).where(
                part_stock.c.part_id == part_id, part_stock.c.location_id == location_id
            ),
            for_update=True,
        )
        return (await self._session.execute(statement)).scalar_one()

    async def for_parts(
        self, part_ids: Collection[UUID], *, for_update: bool = False
    ) -> list[PartStock]:
        ids = list(set(part_ids))
        if not ids:
            return []
        statement = _locked(
            select(PartStock)
            .where(part_stock.c.part_id.in_(ids), part_stock.c.quantity > 0)
            .order_by(part_stock.c.part_id, part_stock.c.location_id),
            for_update,
        )
        return list((await self._session.execute(statement)).scalars())

    async def in_locations(self, location_ids: Collection[UUID]) -> list[PartStock]:
        ids = list(set(location_ids))
        if not ids:
            return []
        statement = select(PartStock).where(
            part_stock.c.location_id.in_(ids), part_stock.c.quantity > 0
        )
        return list((await self._session.execute(statement)).scalars())

    async def totals(self) -> dict[UUID, int]:
        return await self._sums(part_stock.c.part_id)

    async def location_totals(self) -> dict[UUID, int]:
        return await self._sums(part_stock.c.location_id)

    async def _sums(self, column: ColumnElement[UUID]) -> dict[UUID, int]:
        statement = (
            select(column, func.sum(part_stock.c.quantity))
            .where(part_stock.c.quantity > 0)
            .group_by(column)
        )
        rows = await self._session.execute(statement)
        return {row[0]: int(row[1]) for row in rows}


def _open_receipt() -> ColumnElement[bool]:
    return part_receipts.c.stored + part_receipts.c.written_off < part_receipts.c.quantity


class SqlPartReceiptRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, receipt_id: UUID, *, for_update: bool = False) -> PartReceipt | None:
        statement = _locked(select(PartReceipt).where(part_receipts.c.id == receipt_id), for_update)
        return (await self._session.execute(statement)).scalar_one_or_none()

    async def by_ids(self, receipt_ids: Collection[UUID]) -> dict[UUID, PartReceipt]:
        ids = list(set(receipt_ids))
        if not ids:
            return {}
        rows = await self._session.execute(select(PartReceipt).where(part_receipts.c.id.in_(ids)))
        return {receipt.id: receipt for receipt in rows.scalars()}

    async def for_job(self, print_job_id: UUID) -> list[PartReceipt]:
        statement = select(PartReceipt).where(part_receipts.c.print_job_id == print_job_id)
        return list((await self._session.execute(statement)).scalars())

    async def open(
        self, part_id: UUID | None = None, *, for_update: bool = False
    ) -> list[PartReceipt]:
        statement = select(PartReceipt).where(_open_receipt())
        if part_id is not None:
            statement = statement.where(part_receipts.c.part_id == part_id)
        statement = _locked(
            statement.order_by(part_receipts.c.created_at, part_receipts.c.id), for_update
        )
        return list((await self._session.execute(statement)).scalars())

    def add(self, receipt: PartReceipt) -> None:
        self._session.add(receipt)


class SqlPartLedgerRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def add(self, entry: PartLedgerEntry) -> None:
        self._session.add(entry)

    async def for_scan(self, scan_id: UUID) -> list[PartLedgerEntry]:
        return await self._where(part_ledger.c.scan_id == scan_id)

    async def for_unit(self, unit_id: UUID) -> list[PartLedgerEntry]:
        return await self._where(part_ledger.c.unit_id == unit_id)

    async def for_part(self, part_id: UUID, *, limit: int) -> list[PartLedgerEntry]:
        statement = (
            select(PartLedgerEntry)
            .where(part_ledger.c.part_id == part_id)
            .order_by(part_ledger.c.id.desc())
            .limit(limit)
        )
        return list((await self._session.execute(statement)).scalars())

    async def mentions(self, location_id: UUID) -> bool:
        statement = select(
            exists().where(
                or_(
                    part_ledger.c.from_location_id == location_id,
                    part_ledger.c.to_location_id == location_id,
                )
            )
        )
        return bool(await self._session.scalar(statement))

    async def _where(self, condition: ColumnElement[bool]) -> list[PartLedgerEntry]:
        statement = select(PartLedgerEntry).where(condition).order_by(part_ledger.c.id)
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


class SqlManufacturing:
    """The manufacturing module's parts facade, inside this unit of work's transaction."""

    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    async def parts(self, part_ids: Collection[UUID]) -> dict[UUID, PartInfo]:
        return await load_parts(self._uow, part_ids)

    async def part_by_number(self, part_number: str) -> PartInfo | None:
        return await load_part_by_number(self._uow, part_number)

    async def bill_of_materials(self, product_scale_id: UUID) -> list[KitPart]:
        return await load_bill_of_materials(self._uow, product_scale_id)

    async def print_jobs(self, job_ids: Collection[UUID]) -> dict[UUID, PrintJobInfo]:
        return await load_print_jobs(self._uow, job_ids)

    async def print_job_yield(self, job_id: UUID) -> PrintJobYield | None:
        return await load_print_job_yield(self._uow, job_id)


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
    part_stock: SqlPartStockRepository
    receipts: SqlPartReceiptRepository
    part_ledger: SqlPartLedgerRepository
    catalog: SqlCatalog
    manufacturing: SqlManufacturing
    orders: SqlOrders
    staff: SqlStaff

    def _attach(self, session: AsyncSession) -> None:
        start_mappers()
        self.locations = SqlLocationRepository(session)
        self.units = SqlUnitRepository(session)
        self.allocations = SqlAllocationRepository(session)
        self.ledger = SqlLedgerRepository(session)
        self.scans = SqlScanRepository(session)
        self.part_stock = SqlPartStockRepository(session)
        self.receipts = SqlPartReceiptRepository(session)
        self.part_ledger = SqlPartLedgerRepository(session)
        self.catalog = SqlCatalog(self)
        self.manufacturing = SqlManufacturing(self)
        self.orders = SqlOrders(self)
        self.staff = SqlStaff(self)


def inventory_uow_factory(
    session_factory: async_sessionmaker[AsyncSession],
) -> partial[SqlInventoryUnitOfWork]:
    """The factory the inventory services get: a fresh unit of work per call."""
    return partial(SqlInventoryUnitOfWork, session_factory)
