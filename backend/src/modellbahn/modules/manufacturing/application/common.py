"""What the manufacturing use cases share: committing, and the database's answers to it.

The checks before a change answer the usual case with a clear error. The database has the
last word when two requests race; its constraint names say which rule held.
"""

from collections.abc import Callable, Mapping, Sequence
from typing import Final
from uuid import UUID

from modellbahn.modules.manufacturing.application.ports import ManufacturingUnitOfWork
from modellbahn.modules.manufacturing.domain.errors import (
    InvalidFieldError,
    ManufacturingError,
    MaterialInUseError,
    PartInUseError,
    PrinterInUseError,
    PrinterUnavailableError,
)
from modellbahn.modules.manufacturing.domain.model import Part, PrintJob
from modellbahn.platform.uow import ForeignKeyViolationError, UniqueViolationError

_UNIQUE_RULES: Final[Mapping[str, Callable[[], ManufacturingError]]] = {
    "uq_printers_code": lambda: InvalidFieldError("code", "duplicate", "another printer has it"),
    "uq_materials_name": lambda: InvalidFieldError("name", "duplicate", "another material has it"),
    "uq_parts_part_number": lambda: InvalidFieldError(
        "part_number", "duplicate", "another part has it"
    ),
    "print_jobs_one_printing_idx": lambda: PrinterUnavailableError("busy"),
}

# Rows that refer to what is being removed: its history stays, so it cannot go.
_IN_USE: Final[Mapping[str, Callable[[], ManufacturingError]]] = {
    "fk_print_jobs_printer_id_technology_printers": PrinterInUseError,
    "fk_parts_material_id_technology_materials": MaterialInUseError,
    "fk_bom_lines_part_id_scale_code_parts": PartInUseError,
    "fk_print_job_lines_part_id_technology_parts": PartInUseError,
}


async def commit(uow: ManufacturingUnitOfWork) -> None:
    """Commit, answering a violated rule with the domain's error for it."""
    try:
        await uow.commit()
    except UniqueViolationError as exc:
        rule = _UNIQUE_RULES.get(exc.constraint or "")
        if rule is None:
            raise
        raise rule() from exc
    except ForeignKeyViolationError as exc:
        in_use = _IN_USE.get(exc.constraint or "")
        if in_use is None:
            raise
        raise in_use() from exc


async def parts_of(uow: ManufacturingUnitOfWork, jobs: Sequence[PrintJob]) -> dict[UUID, Part]:
    """The parts on the plates of ``jobs``, to name them."""
    return await uow.parts.by_ids({line.part_id for job in jobs for line in job.lines})
