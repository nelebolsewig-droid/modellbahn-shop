"""What the manufacturing use cases need from the outside world, as protocols.

The infrastructure layer implements them; tests may substitute their own.
"""

from collections.abc import Callable, Collection, Sequence
from dataclasses import dataclass
from types import TracebackType
from typing import Protocol, Self
from uuid import UUID

from modellbahn.modules.catalog.contracts.product_scales import ProductScaleLabel
from modellbahn.modules.manufacturing.domain.model import (
    BillOfMaterials,
    BomLine,
    Material,
    Part,
    Printer,
    PrintJob,
    PrintJobStatus,
    StatusReport,
)
from modellbahn.platform.events import DomainEvent


@dataclass(frozen=True, slots=True)
class PartUsage:
    """Where a part is needed: in how many bills of materials, on how many plates."""

    boms: int
    jobs: int


class PrinterRepository(Protocol):
    async def get(self, printer_id: UUID, *, for_update: bool = False) -> Printer | None: ...

    async def by_ids(self, printer_ids: Collection[UUID]) -> dict[UUID, Printer]: ...

    async def all(self) -> Sequence[Printer]:
        """Every printer, by code."""
        ...

    async def code_taken(self, code: str, *, except_id: UUID | None = None) -> bool: ...

    def add(self, printer: Printer) -> None: ...

    async def delete(self, printer: Printer) -> None: ...

    def record(self, report: StatusReport) -> None: ...

    async def history(self, printer_id: UUID, limit: int) -> Sequence[StatusReport]:
        """The printer's latest status reports, the newest first."""
        ...


class MaterialRepository(Protocol):
    async def get(self, material_id: UUID, *, for_update: bool = False) -> Material | None: ...

    async def by_ids(self, material_ids: Collection[UUID]) -> dict[UUID, Material]: ...

    async def all(self) -> Sequence[Material]:
        """Every material, by technology and name."""
        ...

    async def name_taken(self, name: str, *, except_id: UUID | None = None) -> bool: ...

    async def part_counts(self) -> dict[UUID, int]:
        """How many parts each material is used for (only materials with parts)."""
        ...

    def add(self, material: Material) -> None: ...

    async def delete(self, material: Material) -> None: ...


class PartRepository(Protocol):
    async def get(self, part_id: UUID, *, for_update: bool = False) -> Part | None: ...

    async def by_ids(self, part_ids: Collection[UUID]) -> dict[UUID, Part]: ...

    async def search(
        self,
        *,
        scale_code: str | None,
        technology: str | None,
        query: str | None,
        include_archived: bool,
        limit: int,
    ) -> Sequence[Part]:
        """Parts by scale and part number; ``query`` matches number or name."""
        ...

    async def number_taken(self, part_number: str, *, except_id: UUID | None = None) -> bool: ...

    async def usage(self, part_ids: Collection[UUID]) -> dict[UUID, PartUsage]:
        """Where the parts are needed (only parts that are)."""
        ...

    def add(self, part: Part) -> None: ...

    async def delete(self, part: Part) -> None: ...


class BomRepository(Protocol):
    async def get(
        self, product_scale_id: UUID, *, for_update: bool = False
    ) -> BillOfMaterials | None: ...

    async def lines_with_part(self, part_id: UUID) -> Sequence[BomLine]:
        """Every bill of materials line that names the part."""
        ...

    def add(self, bom: BillOfMaterials) -> None: ...

    async def delete(self, bom: BillOfMaterials) -> None: ...


class PrintJobRepository(Protocol):
    async def get(self, job_id: UUID, *, for_update: bool = False) -> PrintJob | None: ...

    async def next_number(self) -> int: ...

    async def open_jobs(self) -> Sequence[PrintJob]:
        """Every job that is queued, printing or in post-processing, the oldest first."""
        ...

    async def printing_on(self, printer_id: UUID, *, for_update: bool = False) -> PrintJob | None:
        """The job printing on the printer right now, if any."""
        ...

    async def queued_count(self, printer_id: UUID) -> int: ...

    async def latest(
        self,
        *,
        statuses: Collection[PrintJobStatus],
        printer_id: UUID | None,
        part_id: UUID | None,
        limit: int,
    ) -> Sequence[PrintJob]:
        """Jobs in these states (all if empty), the newest first."""
        ...

    def add(self, job: PrintJob) -> None: ...


class Catalog(Protocol):
    """The catalogue's facade for products in their scales and the scales themselves."""

    async def product_scales(
        self, product_scale_ids: Collection[UUID]
    ) -> dict[UUID, ProductScaleLabel]: ...

    async def scale_names(self) -> dict[str, str]: ...


class Staff(Protocol):
    """Who did something, by name."""

    async def names(self, account_ids: Collection[UUID]) -> dict[UUID, str]: ...


class ManufacturingUnitOfWork(Protocol):
    """One transaction over the manufacturing repositories (see ``platform.uow``)."""

    @property
    def printers(self) -> PrinterRepository: ...

    @property
    def materials(self) -> MaterialRepository: ...

    @property
    def parts(self) -> PartRepository: ...

    @property
    def boms(self) -> BomRepository: ...

    @property
    def jobs(self) -> PrintJobRepository: ...

    @property
    def catalog(self) -> Catalog: ...

    @property
    def staff(self) -> Staff: ...

    async def __aenter__(self) -> Self: ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...

    def publish(self, *events: DomainEvent) -> None: ...

    async def flush(self) -> None: ...

    async def commit(self) -> None: ...


type UnitOfWorkFactory = Callable[[], ManufacturingUnitOfWork]
