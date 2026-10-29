"""SQLAlchemy implementations of the manufacturing repositories and unit of work.

Repositories only read and stage changes; committing is the unit of work's job.
"""

from collections.abc import Collection, Sequence
from functools import partial
from uuid import UUID

from sqlalchemy import Column, ColumnElement, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from modellbahn.modules.catalog.contracts.product_scales import (
    ProductScaleLabel,
    load_product_scale_labels,
    load_scale_names,
)
from modellbahn.modules.identity.contracts.accounts import load_display_names
from modellbahn.modules.manufacturing.application.ports import PartUsage
from modellbahn.modules.manufacturing.domain.model import (
    OPEN_JOB_STATUSES,
    BillOfMaterials,
    BomLine,
    Material,
    Part,
    Printer,
    PrintJob,
    PrintJobStatus,
    StatusReport,
    Technology,
)
from modellbahn.modules.manufacturing.infrastructure.mapping import start_mappers
from modellbahn.modules.manufacturing.infrastructure.tables import (
    bom_lines,
    boms,
    materials,
    parts,
    print_job_lines,
    print_job_number_seq,
    print_jobs,
    printer_status_reports,
    printers,
)
from modellbahn.platform.uow import UnitOfWork


class SqlPrinterRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, printer_id: UUID, *, for_update: bool = False) -> Printer | None:
        statement = select(Printer).where(printers.c.id == printer_id)
        if for_update:
            statement = statement.with_for_update().execution_options(populate_existing=True)
        return (await self._session.scalars(statement)).one_or_none()

    async def by_ids(self, printer_ids: Collection[UUID]) -> dict[UUID, Printer]:
        if not printer_ids:
            return {}
        statement = select(Printer).where(printers.c.id.in_(list(printer_ids)))
        return {printer.id: printer for printer in await self._session.scalars(statement)}

    async def all(self) -> Sequence[Printer]:
        statement = select(Printer).order_by(printers.c.code)
        return (await self._session.scalars(statement)).all()

    async def code_taken(self, code: str, *, except_id: UUID | None = None) -> bool:
        conditions: list[ColumnElement[bool]] = [printers.c.code == code]
        if except_id is not None:
            conditions.append(printers.c.id != except_id)
        return await _exists(self._session, conditions)

    def add(self, printer: Printer) -> None:
        self._session.add(printer)

    async def delete(self, printer: Printer) -> None:
        await self._session.delete(printer)

    def record(self, report: StatusReport) -> None:
        self._session.add(report)

    async def history(self, printer_id: UUID, limit: int) -> Sequence[StatusReport]:
        statement = (
            select(StatusReport)
            .where(printer_status_reports.c.printer_id == printer_id)
            # UUIDv7: the id breaks ties between reports in the same microsecond.
            .order_by(
                printer_status_reports.c.occurred_at.desc(), printer_status_reports.c.id.desc()
            )
            .limit(limit)
        )
        return (await self._session.scalars(statement)).all()


class SqlMaterialRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, material_id: UUID, *, for_update: bool = False) -> Material | None:
        statement = select(Material).where(materials.c.id == material_id)
        if for_update:
            statement = statement.with_for_update().execution_options(populate_existing=True)
        return (await self._session.scalars(statement)).one_or_none()

    async def by_ids(self, material_ids: Collection[UUID]) -> dict[UUID, Material]:
        if not material_ids:
            return {}
        statement = select(Material).where(materials.c.id.in_(list(material_ids)))
        return {material.id: material for material in await self._session.scalars(statement)}

    async def all(self) -> Sequence[Material]:
        statement = select(Material).order_by(materials.c.technology, materials.c.name)
        return (await self._session.scalars(statement)).all()

    async def name_taken(self, name: str, *, except_id: UUID | None = None) -> bool:
        conditions: list[ColumnElement[bool]] = [materials.c.name == name]
        if except_id is not None:
            conditions.append(materials.c.id != except_id)
        return await _exists(self._session, conditions)

    async def part_counts(self) -> dict[UUID, int]:
        statement = (
            select(parts.c.material_id, func.count())
            .where(parts.c.material_id.is_not(None))
            .group_by(parts.c.material_id)
        )
        return {row[0]: int(row[1]) for row in await self._session.execute(statement)}

    def add(self, material: Material) -> None:
        self._session.add(material)

    async def delete(self, material: Material) -> None:
        await self._session.delete(material)


class SqlPartRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, part_id: UUID, *, for_update: bool = False) -> Part | None:
        statement = select(Part).where(parts.c.id == part_id)
        if for_update:
            statement = statement.with_for_update().execution_options(populate_existing=True)
        return (await self._session.scalars(statement)).one_or_none()

    async def by_ids(self, part_ids: Collection[UUID]) -> dict[UUID, Part]:
        if not part_ids:
            return {}
        statement = select(Part).where(parts.c.id.in_(list(part_ids)))
        return {part.id: part for part in await self._session.scalars(statement)}

    async def search(
        self,
        *,
        scale_code: str | None,
        technology: str | None,
        query: str | None,
        include_archived: bool,
        limit: int,
    ) -> Sequence[Part]:
        statement = select(Part)
        if scale_code is not None:
            statement = statement.where(parts.c.scale_code == scale_code)
        if technology is not None:
            statement = statement.where(parts.c.technology == Technology(technology))
        if not include_archived:
            statement = statement.where(parts.c.active)
        if query is not None:
            pattern = f"%{_escape_like(query)}%"
            statement = statement.where(
                or_(
                    parts.c.part_number.ilike(pattern, escape="\\"),
                    parts.c.name.ilike(pattern, escape="\\"),
                )
            )
        statement = statement.order_by(parts.c.scale_code, parts.c.part_number).limit(limit)
        return (await self._session.scalars(statement)).all()

    async def number_taken(self, part_number: str, *, except_id: UUID | None = None) -> bool:
        conditions: list[ColumnElement[bool]] = [parts.c.part_number == part_number]
        if except_id is not None:
            conditions.append(parts.c.id != except_id)
        return await _exists(self._session, conditions)

    async def usage(self, part_ids: Collection[UUID]) -> dict[UUID, PartUsage]:
        ids = list(set(part_ids))
        if not ids:
            return {}
        in_boms = await self._counts(bom_lines.c.part_id, ids)
        on_plates = await self._counts(print_job_lines.c.part_id, ids)
        return {
            part_id: PartUsage(boms=in_boms.get(part_id, 0), jobs=on_plates.get(part_id, 0))
            for part_id in ids
            if part_id in in_boms or part_id in on_plates
        }

    async def _counts(self, column: Column[UUID], ids: list[UUID]) -> dict[UUID, int]:
        rows = await self._session.execute(
            select(column, func.count()).where(column.in_(ids)).group_by(column)
        )
        return {part_id: int(count) for part_id, count in rows}

    def add(self, part: Part) -> None:
        self._session.add(part)

    async def delete(self, part: Part) -> None:
        await self._session.delete(part)


class SqlBomRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(
        self, product_scale_id: UUID, *, for_update: bool = False
    ) -> BillOfMaterials | None:
        statement = select(BillOfMaterials).where(boms.c.product_scale_id == product_scale_id)
        if for_update:
            statement = statement.with_for_update().execution_options(populate_existing=True)
        return (await self._session.scalars(statement)).one_or_none()

    async def lines_with_part(self, part_id: UUID) -> Sequence[BomLine]:
        statement = select(BomLine).where(bom_lines.c.part_id == part_id)
        return (await self._session.scalars(statement)).all()

    def add(self, bom: BillOfMaterials) -> None:
        self._session.add(bom)

    async def delete(self, bom: BillOfMaterials) -> None:
        await self._session.delete(bom)


class SqlPrintJobRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, job_id: UUID, *, for_update: bool = False) -> PrintJob | None:
        statement = select(PrintJob).where(print_jobs.c.id == job_id)
        if for_update:
            statement = statement.with_for_update().execution_options(populate_existing=True)
        return (await self._session.scalars(statement)).one_or_none()

    async def next_number(self) -> int:
        return int(await self._session.scalar(select(print_job_number_seq.next_value())) or 0)

    async def open_jobs(self) -> Sequence[PrintJob]:
        statement = (
            select(PrintJob)
            .where(print_jobs.c.status.in_(OPEN_JOB_STATUSES))
            .order_by(print_jobs.c.created_at, print_jobs.c.number)
        )
        return (await self._session.scalars(statement)).all()

    async def printing_on(self, printer_id: UUID, *, for_update: bool = False) -> PrintJob | None:
        statement = select(PrintJob).where(
            print_jobs.c.printer_id == printer_id, print_jobs.c.status == PrintJobStatus.PRINTING
        )
        if for_update:
            statement = statement.with_for_update().execution_options(populate_existing=True)
        return (await self._session.scalars(statement)).one_or_none()

    async def queued_count(self, printer_id: UUID) -> int:
        statement = select(func.count()).where(
            print_jobs.c.printer_id == printer_id, print_jobs.c.status == PrintJobStatus.QUEUED
        )
        return int(await self._session.scalar(statement) or 0)

    async def latest(
        self,
        *,
        statuses: Collection[PrintJobStatus],
        printer_id: UUID | None,
        part_id: UUID | None,
        limit: int,
    ) -> Sequence[PrintJob]:
        statement = select(PrintJob)
        if statuses:
            statement = statement.where(print_jobs.c.status.in_(list(statuses)))
        if printer_id is not None:
            statement = statement.where(print_jobs.c.printer_id == printer_id)
        if part_id is not None:
            statement = statement.where(
                print_jobs.c.id.in_(
                    select(print_job_lines.c.job_id).where(print_job_lines.c.part_id == part_id)
                )
            )
        statement = statement.order_by(print_jobs.c.number.desc()).limit(limit)
        return (await self._session.scalars(statement)).all()

    def add(self, job: PrintJob) -> None:
        self._session.add(job)


class SqlCatalog:
    """The catalogue's facade for products in their scales, inside this transaction."""

    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    async def product_scales(
        self, product_scale_ids: Collection[UUID]
    ) -> dict[UUID, ProductScaleLabel]:
        return await load_product_scale_labels(self._uow, product_scale_ids)

    async def scale_names(self) -> dict[str, str]:
        return await load_scale_names(self._uow)


class SqlStaff:
    """The identity module's account facade, inside this transaction."""

    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    async def names(self, account_ids: Collection[UUID]) -> dict[UUID, str]:
        return await load_display_names(self._uow, account_ids)


class SqlManufacturingUnitOfWork(UnitOfWork):
    """Unit of work with the manufacturing repositories attached."""

    printers: SqlPrinterRepository
    materials: SqlMaterialRepository
    parts: SqlPartRepository
    boms: SqlBomRepository
    jobs: SqlPrintJobRepository
    catalog: SqlCatalog
    staff: SqlStaff

    def _attach(self, session: AsyncSession) -> None:
        start_mappers()
        self.printers = SqlPrinterRepository(session)
        self.materials = SqlMaterialRepository(session)
        self.parts = SqlPartRepository(session)
        self.boms = SqlBomRepository(session)
        self.jobs = SqlPrintJobRepository(session)
        self.catalog = SqlCatalog(self)
        self.staff = SqlStaff(self)


def manufacturing_uow_factory(
    session_factory: async_sessionmaker[AsyncSession],
) -> partial[SqlManufacturingUnitOfWork]:
    """The factory the manufacturing services get: a fresh unit of work per call."""
    return partial(SqlManufacturingUnitOfWork, session_factory)


async def _exists(session: AsyncSession, conditions: Sequence[ColumnElement[bool]]) -> bool:
    # Compare with what is stored: flushing a pending change first would hit the unique
    # constraint before this check could answer.
    with session.no_autoflush:
        return bool(await session.scalar(select(exists().where(*conditions))))


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
