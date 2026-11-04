"""What the inventory use cases need from the outside world, as protocols.

The infrastructure layer implements them; tests may substitute their own.
"""

from collections.abc import Collection, Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from types import TracebackType
from typing import Protocol, Self
from uuid import UUID

from modellbahn.modules.catalog.contracts.variants import SaleVariant
from modellbahn.modules.inventory.domain.model import (
    Allocation,
    LedgerEntry,
    Location,
    Scan,
    Unit,
    UnitStatus,
)
from modellbahn.modules.inventory.domain.parts import PartLedgerEntry, PartReceipt, PartStock
from modellbahn.modules.manufacturing.contracts.parts import (
    KitPart,
    PartInfo,
    PrintJobInfo,
    PrintJobYield,
)
from modellbahn.modules.sales.contracts.orders import OrderSummary
from modellbahn.platform.events import DomainEvent


@dataclass(frozen=True, slots=True)
class StockCount:
    """How many units of a variant are in one state."""

    variant_id: UUID
    status: UnitStatus
    count: int


class LocationRepository(Protocol):
    async def get(self, location_id: UUID) -> Location | None: ...

    async def get_by_code(self, code: str, *, for_update: bool = False) -> Location | None: ...

    async def by_ids(self, location_ids: Collection[UUID]) -> dict[UUID, Location]: ...

    async def tree(self) -> list[Location]:
        """Every location, ordered by path (each parent before its children)."""
        ...

    async def subtree(self, location: Location) -> list[Location]:
        """The location and everything below it, ordered by path."""
        ...

    def add(self, location: Location) -> None: ...

    async def delete(self, location: Location) -> None: ...

    async def has_children(self, location_id: UUID) -> bool: ...

    async def in_journal(self, location_id: UUID) -> bool:
        """True if any movement went into or out of the location."""
        ...

    async def unit_counts(self) -> dict[UUID, int]:
        """Units lying in each location (only locations that hold any)."""
        ...


class UnitRepository(Protocol):
    async def get(self, unit_id: UUID, *, for_update: bool = False) -> Unit | None: ...

    async def get_by_code(self, code: str, *, for_update: bool = False) -> Unit | None: ...

    async def existing_codes(self, codes: Collection[str]) -> set[str]: ...

    def add(self, unit: Unit) -> None: ...

    async def in_locations(self, location_ids: Collection[UUID]) -> list[Unit]:
        """Units lying in the locations, oldest first."""
        ...

    async def oldest_labeled(self, variant_id: UUID) -> Unit | None:
        """The oldest unit of the variant that is labelled but not stored yet, locked."""
        ...

    async def oldest_free(self, variant_id: UUID, *, limit: int) -> list[Unit]:
        """Free units of the variant, oldest first, locked; units others lock are skipped."""
        ...

    async def serving(
        self, allocation_ids: Collection[UUID], *, for_update: bool = False
    ) -> dict[UUID, Unit]:
        """The unit that serves each allocation (allocations without one are missing)."""
        ...

    async def counts(self, variant_ids: Collection[UUID] | None = None) -> list[StockCount]:
        """Units per variant and state; ``None`` for every variant."""
        ...


class AllocationRepository(Protocol):
    async def get(self, allocation_id: UUID) -> Allocation | None: ...

    async def by_ids(self, allocation_ids: Collection[UUID]) -> dict[UUID, Allocation]: ...

    async def for_order(self, order_id: UUID, *, for_update: bool = False) -> list[Allocation]:
        """The order's allocations, by line and piece."""
        ...

    async def oldest_backorder(self, variant_id: UUID) -> Allocation | None:
        """The open allocation of the variant that waits longest for a unit, locked.

        Allocations another transaction has locked are skipped.
        """
        ...

    async def backorder_counts(
        self, variant_ids: Collection[UUID] | None = None
    ) -> dict[UUID, int]:
        """Open allocations without a unit, per variant."""
        ...

    def add(self, allocation: Allocation) -> None: ...


class LedgerRepository(Protocol):
    def add(self, entry: LedgerEntry) -> None: ...

    async def for_unit(self, unit_id: UUID) -> list[LedgerEntry]:
        """The unit's history, oldest first."""
        ...

    async def for_scan(self, scan_id: UUID) -> list[LedgerEntry]:
        """What a scan booked, in the order it was booked."""
        ...


class PartStockRepository(Protocol):
    async def lock(self, part_id: UUID, location_id: UUID, *, now: datetime) -> PartStock:
        """The part's stock in the location, locked; created at 0 if there was none."""
        ...

    async def for_parts(
        self, part_ids: Collection[UUID], *, for_update: bool = False
    ) -> list[PartStock]:
        """The locations holding any of the parts (quantity above 0), by part and location.

        Locked rows are locked in that order, so two assemblies never wait for each other
        the other way round.
        """
        ...

    async def in_locations(self, location_ids: Collection[UUID]) -> list[PartStock]:
        """What lies in the locations (quantity above 0)."""
        ...

    async def totals(self) -> dict[UUID, int]:
        """Parts in stock, per part (only parts with any)."""
        ...

    async def location_totals(self) -> dict[UUID, int]:
        """Parts lying in each location (only locations that hold any)."""
        ...


class PartReceiptRepository(Protocol):
    async def get(self, receipt_id: UUID, *, for_update: bool = False) -> PartReceipt | None: ...

    async def by_ids(self, receipt_ids: Collection[UUID]) -> dict[UUID, PartReceipt]: ...

    async def for_job(self, print_job_id: UUID) -> list[PartReceipt]: ...

    async def open(
        self, part_id: UUID | None = None, *, for_update: bool = False
    ) -> list[PartReceipt]:
        """Receipts with parts still waiting for a box, oldest first; of one part or all."""
        ...

    def add(self, receipt: PartReceipt) -> None: ...


class PartLedgerRepository(Protocol):
    def add(self, entry: PartLedgerEntry) -> None: ...

    async def for_scan(self, scan_id: UUID) -> list[PartLedgerEntry]:
        """What a scan booked, in the order it was booked."""
        ...

    async def for_unit(self, unit_id: UUID) -> list[PartLedgerEntry]:
        """The parts a unit was assembled from."""
        ...

    async def for_part(self, part_id: UUID, *, limit: int) -> list[PartLedgerEntry]:
        """The part's latest movements, newest first."""
        ...

    async def mentions(self, location_id: UUID) -> bool:
        """True if any parts went into or out of the location."""
        ...


class ScanRepository(Protocol):
    async def get(self, scan_id: UUID, *, for_update: bool = False) -> Scan | None: ...

    def add(self, scan: Scan) -> None: ...


class Catalog(Protocol):
    """The catalogue's variants, as the shop sells them right now."""

    async def variants(self, variant_ids: Collection[UUID]) -> dict[UUID, SaleVariant]: ...

    async def variant_by_gtin(self, gtin: str) -> SaleVariant | None: ...

    async def product_variants(self, slug: str) -> list[SaleVariant]: ...


class Orders(Protocol):
    """What inventory may ask the sales module."""

    async def summary(self, order_id: UUID) -> OrderSummary | None: ...

    async def numbers(self, order_ids: Collection[UUID]) -> dict[UUID, str]: ...


class Manufacturing(Protocol):
    """What inventory may ask the manufacturing module: parts, kits, finished plates."""

    async def parts(self, part_ids: Collection[UUID]) -> dict[UUID, PartInfo]: ...

    async def part_by_number(self, part_number: str) -> PartInfo | None: ...

    async def bill_of_materials(self, product_scale_id: UUID) -> list[KitPart]: ...

    async def print_jobs(self, job_ids: Collection[UUID]) -> dict[UUID, PrintJobInfo]: ...

    async def print_job_yield(self, job_id: UUID) -> PrintJobYield | None: ...


class Staff(Protocol):
    """Who booked what: the identity module's display names."""

    async def names(self, account_ids: Collection[UUID]) -> dict[UUID, str]: ...


class InventoryUnitOfWork(Protocol):
    """One transaction over the inventory repositories (see ``platform.uow``)."""

    @property
    def locations(self) -> LocationRepository: ...

    @property
    def units(self) -> UnitRepository: ...

    @property
    def allocations(self) -> AllocationRepository: ...

    @property
    def ledger(self) -> LedgerRepository: ...

    @property
    def scans(self) -> ScanRepository: ...

    @property
    def part_stock(self) -> PartStockRepository: ...

    @property
    def receipts(self) -> PartReceiptRepository: ...

    @property
    def part_ledger(self) -> PartLedgerRepository: ...

    @property
    def catalog(self) -> Catalog: ...

    @property
    def manufacturing(self) -> Manufacturing: ...

    @property
    def orders(self) -> Orders: ...

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


class LabelSheet(StrEnum):
    """The label stock the printer is loaded with."""

    A4_70X37 = "a4_70x37"
    """A4 sheets with 3 x 8 labels of 70 x 37 mm (e.g. Avery Zweckform 3474), any printer."""
    QL_62X29 = "ql_62x29"
    """Brother QL with the 62 mm endless roll (DK-22205), one label of 62 x 29 mm per page."""


@dataclass(frozen=True, slots=True)
class Label:
    """What one label shows: barcodes for scanners and tills, and text for people.

    A unit's label carries the variant's EAN-13, which the till (SumUp) knows the
    article by, and a Code 128 with the unit's own code for the workshop's scanner. A
    location's label carries only the Code 128 with its code, and so does a part's label
    (on the box the parts lie in) with the part number.
    """

    caption: str
    """What the label marks (``Einheit``, ``Lagerplatz``, ``Teil``), set small at the top."""
    code_text: str
    """The code as people read it: ``7KQ2 X9F4 MZ``, ``R02-F04-B12`` or a part number."""
    code128: str
    """The data of the Code 128: the unit code, the location code or the part number."""
    title: str
    detail: str
    reference: str
    """A line in monospace: the article number, or the location's path."""
    ean13: str | None = None
    """The variant's EAN-13 (units only)."""


class LabelRenderer(Protocol):
    """Turns label contents into a printable document (PDF)."""

    def render(self, labels: Sequence[Label], *, sheet: LabelSheet, skip: int) -> bytes:
        """``skip`` leaves that many labels of a started A4 sheet empty."""
        ...
