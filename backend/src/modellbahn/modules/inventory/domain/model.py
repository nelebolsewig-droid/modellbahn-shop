"""The inventory model: where things lie, every finished piece on its own, and who gets it.

*Locations* form a tree: site → shelf → compartment → box (and staging areas on the
site, such as the packing table). Only compartments, boxes and staging areas hold goods.
A location's code is printed on its label, so it never changes and the tree is never
rearranged; the name may change.

A *unit* is one finished piece with its own code, from labelling to shipping:

    labeled ─▶ in_stock ─▶ allocated ─▶ picked ─▶ shipped
                  ▲            │           │
                  └─ release ──┘           └─ release (order cancelled) ─▶ labeled

Any unit that has not left the workshop can be scrapped. Every change of a unit returns
a :class:`Movement`, which the journal keeps for good (``stock_ledger``); undoing a scan
books the movements backwards instead of deleting them.

An *allocation* is one piece of an order line. It is backordered while no unit points to
it, reserved while one is allocated to it, picked once that unit is taken from the shelf.

Plain dataclasses without any framework, mapped imperatively by the infrastructure.
Every method that depends on time takes ``now``.
"""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Final
from uuid import UUID

from modellbahn.modules.inventory.domain.codes import SEGMENT
from modellbahn.modules.inventory.domain.errors import InvalidFieldError, InvalidUnitStateError
from modellbahn.platform.events import JsonObject
from modellbahn.platform.ids import new_id

LOCATION_NAME_MAX_LENGTH: Final = 60
SCRAP_NOTE_MAX_LENGTH: Final = 200
UNITS_PER_BATCH_MAX: Final = 200
UNDO_WINDOW_SECONDS: Final = 600


def _text(value: str, field_name: str, max_length: int) -> str:
    cleaned = " ".join(value.split())
    if len(cleaned) > max_length:
        raise InvalidFieldError(field_name, "too_long", f"at most {max_length} characters")
    return cleaned


# --- Locations ------------------------------------------------------------------------


class LocationKind(StrEnum):
    SITE = "site"
    SHELF = "shelf"
    COMPARTMENT = "compartment"
    BOX = "box"
    STAGING = "staging"


# Which kind may sit inside which: a box goes into a compartment or straight on a shelf.
_PARENT_KINDS: Final[dict[LocationKind, frozenset[LocationKind | None]]] = {
    LocationKind.SITE: frozenset({None}),
    LocationKind.SHELF: frozenset({LocationKind.SITE}),
    LocationKind.COMPARTMENT: frozenset({LocationKind.SHELF}),
    LocationKind.BOX: frozenset({LocationKind.SHELF, LocationKind.COMPARTMENT}),
    LocationKind.STAGING: frozenset({LocationKind.SITE}),
}
_HOLDS_GOODS: Final = frozenset({LocationKind.COMPARTMENT, LocationKind.BOX, LocationKind.STAGING})


@dataclass(eq=False, kw_only=True)
class Location:
    """A place in the workshop with a label: ``R02-F04-B12`` on path ``LAGER.R02.F04.B12``."""

    id: UUID
    parent_id: UUID | None
    code: str
    path: str
    kind: LocationKind
    name: str
    created_at: datetime
    updated_at: datetime

    @classmethod
    def create(
        cls,
        *,
        parent: "Location | None",
        segment: str,
        kind: LocationKind,
        name: str,
        now: datetime,
    ) -> "Location":
        """A new location below ``parent``; a site has none.

        Directly on a site the code is the segment itself (``R02``); further down it is
        the parent's code and the segment (``R02-F04``).
        """
        cleaned = segment.strip().upper()
        if not SEGMENT.fullmatch(cleaned):
            raise InvalidFieldError("segment", "invalid", "1 to 8 letters or digits")
        parent_kind = parent.kind if parent is not None else None
        if parent_kind not in _PARENT_KINDS[kind]:
            raise InvalidFieldError(
                "parent_code", "invalid_parent", f"a {kind} cannot be placed there"
            )
        if parent is None:
            code, path = cleaned, cleaned
        elif parent.kind is LocationKind.SITE:
            code, path = cleaned, f"{parent.path}.{cleaned}"
        else:
            code, path = f"{parent.code}-{cleaned}", f"{parent.path}.{cleaned}"
        return cls(
            id=new_id(),
            parent_id=parent.id if parent is not None else None,
            code=code,
            path=path,
            kind=kind,
            name=_text(name, "name", LOCATION_NAME_MAX_LENGTH),
            created_at=now,
            updated_at=now,
        )

    @property
    def holds_goods(self) -> bool:
        return self.kind in _HOLDS_GOODS

    @property
    def depth(self) -> int:
        return self.path.count(".")

    def rename(self, name: str, now: datetime) -> None:
        self.name = _text(name, "name", LOCATION_NAME_MAX_LENGTH)
        self.updated_at = now


# --- Units ----------------------------------------------------------------------------


class UnitStatus(StrEnum):
    LABELED = "labeled"
    IN_STOCK = "in_stock"
    ALLOCATED = "allocated"
    PICKED = "picked"
    SHIPPED = "shipped"
    SCRAPPED = "scrapped"


ON_SHELF: Final = frozenset({UnitStatus.IN_STOCK, UnitStatus.ALLOCATED})
"""States in which a unit lies in a location."""
TAKEN: Final = frozenset({UnitStatus.ALLOCATED, UnitStatus.PICKED, UnitStatus.SHIPPED})
"""States in which a unit serves an allocation."""
GONE: Final = frozenset({UnitStatus.SHIPPED, UnitStatus.SCRAPPED})


class MovementReason(StrEnum):
    LABEL = "label"
    PUT_AWAY = "put_away"
    MOVE = "move"
    ALLOCATE = "allocate"
    RELEASE = "release"
    PICK = "pick"
    SHIP = "ship"
    SCRAP = "scrap"
    UNDO = "undo"


@dataclass(frozen=True, slots=True)
class Movement:
    """One change of a unit, as the journal keeps it: from which state and place to which."""

    unit_id: UUID
    variant_id: UUID
    reason: MovementReason
    from_status: UnitStatus | None
    to_status: UnitStatus
    from_location_id: UUID | None
    to_location_id: UUID | None
    allocation_id: UUID | None
    """The allocation the unit served before or serves afterwards (allocate, release, pick)."""


@dataclass(eq=False, kw_only=True)
class Unit:
    """One finished piece with its own code; ``variant_id`` names what it is."""

    id: UUID
    code: str
    variant_id: UUID
    status: UnitStatus
    location_id: UUID | None
    allocation_id: UUID | None
    created_at: datetime
    updated_at: datetime
    scrap_note: str = ""

    @classmethod
    def label(cls, *, variant_id: UUID, code: str, now: datetime) -> tuple["Unit", Movement]:
        """A new unit whose label is about to be printed; it is not in a location yet."""
        unit = cls(
            id=new_id(),
            code=code,
            variant_id=variant_id,
            status=UnitStatus.LABELED,
            location_id=None,
            allocation_id=None,
            created_at=now,
            updated_at=now,
        )
        return unit, unit._movement(
            MovementReason.LABEL, from_status=None, from_location_id=None, allocation_id=None
        )

    @property
    def is_free(self) -> bool:
        """In a location and promised to nobody: what the shop can sell straight away."""
        return self.status is UnitStatus.IN_STOCK

    def put_away(self, location: Location, now: datetime) -> Movement:
        """Into ``location``: a labelled unit is stored, a stored one moves there."""
        if not location.holds_goods:
            raise InvalidUnitStateError(f"a {location.kind} holds no goods")
        if self.status not in {UnitStatus.LABELED, *ON_SHELF}:
            raise InvalidUnitStateError(f"a unit that is {self.status} cannot be put away")
        if self.location_id == location.id:
            raise InvalidUnitStateError("the unit is already there")
        reason = (
            MovementReason.PUT_AWAY if self.status is UnitStatus.LABELED else MovementReason.MOVE
        )
        before = self._state()
        if self.status is UnitStatus.LABELED:
            self.status = UnitStatus.IN_STOCK
        self.location_id = location.id
        return self._changed(reason, before, self.allocation_id, now)

    def allocate(self, allocation_id: UUID, now: datetime) -> Movement:
        """Reserve the unit for one piece of an order; it stays where it lies."""
        if self.status is not UnitStatus.IN_STOCK:
            raise InvalidUnitStateError(f"a unit that is {self.status} cannot be allocated")
        before = self._state()
        self.status = UnitStatus.ALLOCATED
        self.allocation_id = allocation_id
        return self._changed(MovementReason.ALLOCATE, before, allocation_id, now)

    def release(self, now: datetime) -> Movement:
        """Free the unit from its allocation (order cancelled, or another unit was picked).

        A reserved unit is free stock where it lies; a picked one is in somebody's hands
        and counts as labelled until it is put away again.
        """
        if self.status not in {UnitStatus.ALLOCATED, UnitStatus.PICKED}:
            raise InvalidUnitStateError(f"a unit that is {self.status} cannot be released")
        before = self._state()
        allocation_id = self.allocation_id
        self.status = (
            UnitStatus.IN_STOCK if self.status is UnitStatus.ALLOCATED else UnitStatus.LABELED
        )
        self.allocation_id = None
        return self._changed(MovementReason.RELEASE, before, allocation_id, now)

    def pick(self, now: datetime) -> Movement:
        """Take the reserved unit off the shelf for packing."""
        if self.status is not UnitStatus.ALLOCATED:
            raise InvalidUnitStateError(f"a unit that is {self.status} cannot be picked")
        before = self._state()
        self.status = UnitStatus.PICKED
        self.location_id = None
        return self._changed(MovementReason.PICK, before, self.allocation_id, now)

    def ship(self, now: datetime) -> Movement:
        if self.status is not UnitStatus.PICKED:
            raise InvalidUnitStateError(f"a unit that is {self.status} cannot be shipped")
        before = self._state()
        self.status = UnitStatus.SHIPPED
        return self._changed(MovementReason.SHIP, before, self.allocation_id, now)

    def scrap(self, note: str, now: datetime) -> Movement:
        """Broken or lost: the unit leaves the stock; an allocation it served is open again."""
        if self.status in GONE:
            raise InvalidUnitStateError(f"a unit that is {self.status} cannot be scrapped")
        before = self._state()
        allocation_id = self.allocation_id
        self.scrap_note = _text(note, "note", SCRAP_NOTE_MAX_LENGTH)
        self.status = UnitStatus.SCRAPPED
        self.location_id = None
        self.allocation_id = None
        return self._changed(MovementReason.SCRAP, before, allocation_id, now)

    def is_in(self, movement: Movement) -> bool:
        """True if the unit is still exactly where ``movement`` left it."""
        expected_allocation = movement.allocation_id if movement.to_status in TAKEN else None
        return (
            self.status is movement.to_status
            and self.location_id == movement.to_location_id
            and self.allocation_id == expected_allocation
        )

    def revert(self, movement: Movement, now: datetime) -> Movement:
        """Book ``movement`` backwards (undoing a scan); the unit must not have moved on."""
        if movement.from_status is None or not self.is_in(movement):
            raise InvalidUnitStateError("the unit has changed since")
        before = self._state()
        self.status = movement.from_status
        self.location_id = movement.from_location_id
        self.allocation_id = movement.allocation_id if movement.from_status in TAKEN else None
        if movement.reason is MovementReason.SCRAP:
            self.scrap_note = ""
        return self._changed(MovementReason.UNDO, before, movement.allocation_id, now)

    def _state(self) -> tuple[UnitStatus, UUID | None]:
        return self.status, self.location_id

    def _changed(
        self,
        reason: MovementReason,
        before: tuple[UnitStatus, UUID | None],
        allocation_id: UUID | None,
        now: datetime,
    ) -> Movement:
        self.updated_at = now
        from_status, from_location_id = before
        return self._movement(
            reason,
            from_status=from_status,
            from_location_id=from_location_id,
            allocation_id=allocation_id,
        )

    def _movement(
        self,
        reason: MovementReason,
        *,
        from_status: UnitStatus | None,
        from_location_id: UUID | None,
        allocation_id: UUID | None,
    ) -> Movement:
        return Movement(
            unit_id=self.id,
            variant_id=self.variant_id,
            reason=reason,
            from_status=from_status,
            to_status=self.status,
            from_location_id=from_location_id,
            to_location_id=self.location_id,
            allocation_id=allocation_id,
        )


# --- Allocations ----------------------------------------------------------------------


class AllocationStatus(StrEnum):
    OPEN = "open"
    SHIPPED = "shipped"
    RELEASED = "released"


@dataclass(eq=False, kw_only=True)
class Allocation:
    """One piece of an order line that the workshop owes.

    Whether it is backordered, reserved or picked follows from the unit pointing to it;
    the allocation itself only knows whether it is still open.
    """

    id: UUID
    order_id: UUID
    order_line_id: UUID
    variant_id: UUID
    piece: int
    """Which piece of the line (0, 1, 2 …), so that a line of three has three allocations."""
    status: AllocationStatus
    created_at: datetime
    updated_at: datetime

    @classmethod
    def open(
        cls, *, order_id: UUID, order_line_id: UUID, variant_id: UUID, piece: int, now: datetime
    ) -> "Allocation":
        return cls(
            id=new_id(),
            order_id=order_id,
            order_line_id=order_line_id,
            variant_id=variant_id,
            piece=piece,
            status=AllocationStatus.OPEN,
            created_at=now,
            updated_at=now,
        )

    def ship(self, now: datetime) -> None:
        if self.status is AllocationStatus.OPEN:
            self.status = AllocationStatus.SHIPPED
            self.updated_at = now

    def release(self, now: datetime) -> None:
        if self.status is AllocationStatus.OPEN:
            self.status = AllocationStatus.RELEASED
            self.updated_at = now


# --- Journal --------------------------------------------------------------------------


@dataclass(eq=False, kw_only=True)
class LedgerEntry:
    """A movement as booked: who, when, through which scan, possibly undoing another entry."""

    id: int | None
    unit_id: UUID
    variant_id: UUID
    reason: MovementReason
    from_status: UnitStatus | None
    to_status: UnitStatus
    from_location_id: UUID | None
    to_location_id: UUID | None
    allocation_id: UUID | None
    scan_id: UUID | None
    staff_id: UUID | None
    reverses_id: int | None
    occurred_at: datetime

    @classmethod
    def book(
        cls,
        movement: Movement,
        *,
        scan_id: UUID | None,
        staff_id: UUID | None,
        now: datetime,
        reverses_id: int | None = None,
    ) -> "LedgerEntry":
        return cls(
            id=None,
            unit_id=movement.unit_id,
            variant_id=movement.variant_id,
            reason=movement.reason,
            from_status=movement.from_status,
            to_status=movement.to_status,
            from_location_id=movement.from_location_id,
            to_location_id=movement.to_location_id,
            allocation_id=movement.allocation_id,
            scan_id=scan_id,
            staff_id=staff_id,
            reverses_id=reverses_id,
            occurred_at=now,
        )

    def movement(self) -> Movement:
        return Movement(
            unit_id=self.unit_id,
            variant_id=self.variant_id,
            reason=self.reason,
            from_status=self.from_status,
            to_status=self.to_status,
            from_location_id=self.from_location_id,
            to_location_id=self.to_location_id,
            allocation_id=self.allocation_id,
        )


# --- Scans ----------------------------------------------------------------------------


class ScanMode(StrEnum):
    PUT_AWAY = "put_away"
    PICK = "pick"
    LOOKUP = "lookup"


class ScanOutcome(StrEnum):
    APPLIED = "applied"
    """Something was booked; the scan can be undone for a while."""
    SELECTED = "selected"
    """The scan chose the context (the location to put away into); nothing booked."""
    INFO = "info"
    """Looked up, nothing booked."""
    REJECTED = "rejected"
    """Known code, but wrong here (wrong article, wrong state); nothing booked."""
    UNKNOWN = "unknown"
    """No unit, location or variant has this code."""


@dataclass(eq=False, kw_only=True)
class Scan:
    """A scan as received, with the answer given; a repeat of the same id gets that answer.

    The id comes from the device, so a scan sent again after a lost connection is
    recognised instead of booked twice.
    """

    id: UUID
    staff_id: UUID
    mode: ScanMode
    raw: str
    source: str
    context: dict[str, str]
    outcome: ScanOutcome
    response: JsonObject
    created_at: datetime
    undone_at: datetime | None = None

    def matches(self, *, mode: ScanMode, raw: str, context: dict[str, str]) -> bool:
        """True if a repeated request is the same scan (not a reused id)."""
        return self.mode is mode and self.raw == raw and self.context == context

    def can_undo(self, now: datetime) -> bool:
        return (
            self.outcome is ScanOutcome.APPLIED
            and self.undone_at is None
            and (now - self.created_at).total_seconds() <= UNDO_WINDOW_SECONDS
        )

    def mark_undone(self, now: datetime) -> None:
        self.undone_at = now
