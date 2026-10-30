"""Read-only facade for the stock: parts, bills of materials, and what a plate yielded.

It runs SQL, so a domain layer must not import it (the pure-domain contract says so).
"""

from collections.abc import Collection
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final
from uuid import UUID

from sqlalchemy import ColumnElement, Row, select

from modellbahn.modules.manufacturing.domain.model import PrintJobStatus, Technology
from modellbahn.modules.manufacturing.infrastructure.tables import (
    bom_lines,
    parts,
    print_job_lines,
    print_jobs,
    printers,
)
from modellbahn.platform.uow import UnitOfWork

__all__ = [
    "PART_REFERENCE",
    "PRINT_JOB_LINE_REFERENCE",
    "KitPart",
    "PartInfo",
    "PrintJobInfo",
    "PrintJobYield",
    "Technology",
    "load_bill_of_materials",
    "load_part_by_number",
    "load_parts",
    "load_print_job_yield",
    "load_print_jobs",
]

PART_REFERENCE: Final = "manufacturing.parts.id"
"""Target for another module's foreign key to a part (``RESTRICT``: a part with stock
stays; it can be archived). Importing it also puts the manufacturing tables on the
shared metadata, which SQLAlchemy needs to resolve the key."""

PRINT_JOB_LINE_REFERENCE: Final = (
    "manufacturing.print_job_lines.job_id",
    "manufacturing.print_job_lines.part_id",
)
"""Target for a composite foreign key ``(print_job_id, part_id)`` (``RESTRICT``): what
came off a plate refers to a line of that plate."""


@dataclass(frozen=True, slots=True)
class PartInfo:
    """A part as the stock names it: number, name, scale and technology."""

    part_id: UUID
    part_number: str
    name: str
    scale_code: str
    technology: Technology
    active: bool


@dataclass(frozen=True, slots=True)
class KitPart:
    """One line of a bill of materials: so many of a part go into one kit."""

    part: PartInfo
    quantity: int


@dataclass(frozen=True, slots=True)
class PrintJobInfo:
    """A print job as people name it: Druck 17 on D04."""

    job_id: UUID
    number: int
    printer_code: str
    status: PrintJobStatus
    finished_at: datetime | None


@dataclass(frozen=True, slots=True)
class PrintJobYield:
    """The good parts of a finished plate, per part (lines without good parts left out)."""

    job: PrintJobInfo
    good: dict[UUID, int]


def _part_info(row: Row[*tuple[Any, ...]]) -> PartInfo:
    return PartInfo(
        part_id=row.id,
        part_number=row.part_number,
        name=row.name,
        scale_code=row.scale_code,
        technology=Technology(row.technology),
        active=row.active,
    )


_PART_COLUMNS: Final = (
    parts.c.id,
    parts.c.part_number,
    parts.c.name,
    parts.c.scale_code,
    parts.c.technology,
    parts.c.active,
)


async def _parts_where(uow: UnitOfWork, condition: ColumnElement[bool]) -> list[PartInfo]:
    rows = await uow.session.execute(select(*_PART_COLUMNS).where(condition))
    return [_part_info(row) for row in rows]


async def load_parts(uow: UnitOfWork, part_ids: Collection[UUID]) -> dict[UUID, PartInfo]:
    """The parts among ``part_ids``; unknown ids are left out."""
    ids = list(set(part_ids))
    if not ids:
        return {}
    return {part.part_id: part for part in await _parts_where(uow, parts.c.id.in_(ids))}


async def load_part_by_number(uow: UnitOfWork, part_number: str) -> PartInfo | None:
    """The part with this number (upper case), if any: a scanned part label."""
    found = await _parts_where(uow, parts.c.part_number == part_number)
    return found[0] if found else None


async def load_bill_of_materials(uow: UnitOfWork, product_scale_id: UUID) -> list[KitPart]:
    """The parts of one kit of the product in its scale, in the list's order (empty if none)."""
    rows = await uow.session.execute(
        select(*_PART_COLUMNS, bom_lines.c.quantity)
        .join(bom_lines, bom_lines.c.part_id == parts.c.id)
        .where(bom_lines.c.product_scale_id == product_scale_id)
        .order_by(bom_lines.c.position)
    )
    return [KitPart(part=_part_info(row), quantity=int(row.quantity)) for row in rows]


async def load_print_jobs(uow: UnitOfWork, job_ids: Collection[UUID]) -> dict[UUID, PrintJobInfo]:
    """The print jobs among ``job_ids``; unknown ids are left out."""
    ids = list(set(job_ids))
    if not ids:
        return {}
    rows = await uow.session.execute(
        select(
            print_jobs.c.id,
            print_jobs.c.number,
            print_jobs.c.status,
            print_jobs.c.finished_at,
            printers.c.code,
        )
        .join(printers, printers.c.id == print_jobs.c.printer_id)
        .where(print_jobs.c.id.in_(ids))
    )
    return {
        row.id: PrintJobInfo(
            job_id=row.id,
            number=row.number,
            printer_code=row.code,
            status=PrintJobStatus(row.status),
            finished_at=row.finished_at,
        )
        for row in rows
    }


async def load_print_job_yield(uow: UnitOfWork, job_id: UUID) -> PrintJobYield | None:
    """The good parts of the job, if it is done; ``None`` for any other job."""
    job = (await load_print_jobs(uow, [job_id])).get(job_id)
    if job is None or job.status is not PrintJobStatus.DONE:
        return None
    rows = await uow.session.execute(
        select(print_job_lines.c.part_id, print_job_lines.c.good)
        .where(print_job_lines.c.job_id == job_id, print_job_lines.c.good > 0)
        .order_by(print_job_lines.c.position)
    )
    return PrintJobYield(job=job, good={row.part_id: int(row.good) for row in rows})
