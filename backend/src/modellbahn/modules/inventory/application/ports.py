"""What the inventory use cases need from the outside world, as protocols.

The infrastructure layer implements them; tests may substitute their own.
"""

from collections.abc import Collection, Sequence
from dataclasses import dataclass
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
    def catalog(self) -> Catalog: ...

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
    """What one label shows: a QR code, the code in large type, two lines of text."""

    caption: str
    """What the label marks (``Einheit``, ``Lagerplatz``), set small above the code."""
    qr_payload: str
    """The URL in the QR code; a phone camera opens the matching page."""
    code_text: str
    title: str
    detail: str
    reference: str
    """The bottom line in monospace: the article number, or the location's path."""


class LabelRenderer(Protocol):
    """Turns label contents into a printable document (PDF)."""

    def render(self, labels: Sequence[Label], *, sheet: LabelSheet, skip: int) -> bytes:
        """``skip`` leaves that many labels of a started A4 sheet empty."""
        ...
