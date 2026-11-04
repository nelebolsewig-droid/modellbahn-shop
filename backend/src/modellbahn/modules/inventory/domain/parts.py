"""The parts store: printed parts by the box, from the printer to the kit.

Parts are not single pieces like units; the store counts them per part and location
(``PartStock``). Their way through the workshop:

    finished plate ─▶ receipt ─▶ box ─▶ assembly into a unit
                        │          │
                        │          └─ count (correction after counting a box)
                        └─ write off (lost between printer and shelf)

A *receipt* (*Eingang*) holds the good parts of one part from one finished plate until
somebody puts them into a box. Every change of a quantity is a :class:`PartMovement`,
which the parts journal keeps for good (``part_ledger``); undoing a scan books the
movement backwards. An assembly names the unit it made, so every kit knows which boxes
its parts came from.

Plain dataclasses without any framework, mapped imperatively by the infrastructure.
"""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Final
from uuid import UUID

from modellbahn.modules.inventory.domain.errors import (
    InsufficientPartsError,
    InvalidFieldError,
    InvalidReceiptStateError,
)
from modellbahn.platform.ids import new_id

PART_QUANTITY_MAX: Final = 100_000
"""More parts than fit in any box: a typing error rather than a count."""
PART_NOTE_MAX_LENGTH: Final = 200
KITS_PER_ASSEMBLY_MAX: Final = 50


def _quantity(value: int, field_name: str = "quantity") -> int:
    if not 1 <= value <= PART_QUANTITY_MAX:
        raise InvalidFieldError(field_name, "out_of_range", f"between 1 and {PART_QUANTITY_MAX}")
    return value


def _note(value: str) -> str:
    cleaned = " ".join(value.split())
    if len(cleaned) > PART_NOTE_MAX_LENGTH:
        raise InvalidFieldError("note", "too_long", f"at most {PART_NOTE_MAX_LENGTH} characters")
    return cleaned


class PartMovementReason(StrEnum):
    RECEIVE = "receive"
    """From a receipt into a location."""
    ASSEMBLE = "assemble"
    """Out of a location into a unit."""
    COUNT = "count"
    """A correction after counting: into a location (found) or out of it (missing)."""
    WRITE_OFF = "write_off"
    """The rest of a receipt never reached a shelf."""
    UNDO = "undo"


@dataclass(frozen=True, slots=True)
class PartMovement:
    """Parts going from somewhere to somewhere: a receipt, a location, a unit, or nowhere."""

    part_id: UUID
    reason: PartMovementReason
    quantity: int
    from_location_id: UUID | None
    to_location_id: UUID | None
    receipt_id: UUID | None = None
    unit_id: UUID | None = None
    """The unit assembled from the parts."""
    note: str = ""


@dataclass(eq=False, kw_only=True)
class PartStock:
    """How many of a part lie in one location; never negative."""

    part_id: UUID
    location_id: UUID
    quantity: int
    updated_at: datetime

    @classmethod
    def empty(cls, *, part_id: UUID, location_id: UUID, now: datetime) -> "PartStock":
        return cls(part_id=part_id, location_id=location_id, quantity=0, updated_at=now)

    def put(self, quantity: int, now: datetime) -> None:
        self.quantity += _quantity(quantity)
        self.updated_at = now

    def take(self, quantity: int, now: datetime) -> None:
        if _quantity(quantity) > self.quantity:
            raise InsufficientPartsError
        self.quantity -= quantity
        self.updated_at = now

    def assemble(self, quantity: int, unit_id: UUID, now: datetime) -> PartMovement:
        """Take parts for one unit."""
        self.take(quantity, now)
        return PartMovement(
            part_id=self.part_id,
            reason=PartMovementReason.ASSEMBLE,
            quantity=quantity,
            from_location_id=self.location_id,
            to_location_id=None,
            unit_id=unit_id,
        )

    def count(self, counted: int, note: str, now: datetime) -> PartMovement | None:
        """Set the quantity to what was counted; ``None`` if it was right."""
        if not 0 <= counted <= PART_QUANTITY_MAX:
            raise InvalidFieldError(
                "quantity", "out_of_range", f"between 0 and {PART_QUANTITY_MAX}"
            )
        difference = counted - self.quantity
        if difference == 0:
            return None
        cleaned = _note(note)
        self.quantity = counted
        self.updated_at = now
        return PartMovement(
            part_id=self.part_id,
            reason=PartMovementReason.COUNT,
            quantity=abs(difference),
            from_location_id=self.location_id if difference < 0 else None,
            to_location_id=self.location_id if difference > 0 else None,
            note=cleaned,
        )


@dataclass(eq=False, kw_only=True)
class PartReceipt:
    """The good parts of one part from one finished plate, on their way into a box.

    Open while not all of them are stored or written off.
    """

    id: UUID
    print_job_id: UUID
    part_id: UUID
    quantity: int
    stored: int
    written_off: int
    created_at: datetime
    updated_at: datetime

    @classmethod
    def arrive(
        cls, *, print_job_id: UUID, part_id: UUID, quantity: int, now: datetime
    ) -> "PartReceipt":
        return cls(
            id=new_id(),
            print_job_id=print_job_id,
            part_id=part_id,
            quantity=_quantity(quantity),
            stored=0,
            written_off=0,
            created_at=now,
            updated_at=now,
        )

    @property
    def open(self) -> int:
        """Parts still waiting to be put into a box."""
        return self.quantity - self.stored - self.written_off

    def store(self, stock: PartStock, now: datetime) -> PartMovement:
        """Put every open part of the receipt into the stock's location."""
        if stock.part_id != self.part_id:
            raise InvalidReceiptStateError("another part")
        quantity = self.open
        if quantity == 0:
            raise InvalidReceiptStateError("nothing open")
        stock.put(quantity, now)
        self.stored += quantity
        self.updated_at = now
        return PartMovement(
            part_id=self.part_id,
            reason=PartMovementReason.RECEIVE,
            quantity=quantity,
            from_location_id=None,
            to_location_id=stock.location_id,
            receipt_id=self.id,
        )

    def write_off(self, note: str, now: datetime) -> PartMovement:
        """The open parts never reached a shelf (lost, broken on the way)."""
        quantity = self.open
        if quantity == 0:
            raise InvalidReceiptStateError("nothing open")
        cleaned = _note(note)
        self.written_off += quantity
        self.updated_at = now
        return PartMovement(
            part_id=self.part_id,
            reason=PartMovementReason.WRITE_OFF,
            quantity=quantity,
            from_location_id=None,
            to_location_id=None,
            receipt_id=self.id,
            note=cleaned,
        )

    def unstore(self, movement: PartMovement, stock: PartStock, now: datetime) -> PartMovement:
        """Book a :meth:`store` backwards (undoing its scan): out of the box, open again."""
        if (
            movement.reason is not PartMovementReason.RECEIVE
            or movement.receipt_id != self.id
            or movement.to_location_id != stock.location_id
        ):
            raise InvalidReceiptStateError("not this receipt's booking")
        if movement.quantity > self.stored:
            raise InvalidReceiptStateError("changed since")
        stock.take(movement.quantity, now)
        self.stored -= movement.quantity
        self.updated_at = now
        return PartMovement(
            part_id=self.part_id,
            reason=PartMovementReason.UNDO,
            quantity=movement.quantity,
            from_location_id=stock.location_id,
            to_location_id=None,
            receipt_id=self.id,
        )


@dataclass(eq=False, kw_only=True)
class PartLedgerEntry:
    """A part movement as booked: who, when, through which scan, possibly undoing another."""

    id: int | None
    part_id: UUID
    reason: PartMovementReason
    quantity: int
    from_location_id: UUID | None
    to_location_id: UUID | None
    receipt_id: UUID | None
    unit_id: UUID | None
    note: str
    scan_id: UUID | None
    staff_id: UUID | None
    reverses_id: int | None
    occurred_at: datetime

    @classmethod
    def book(
        cls,
        movement: PartMovement,
        *,
        scan_id: UUID | None,
        staff_id: UUID | None,
        now: datetime,
        reverses_id: int | None = None,
    ) -> "PartLedgerEntry":
        return cls(
            id=None,
            part_id=movement.part_id,
            reason=movement.reason,
            quantity=movement.quantity,
            from_location_id=movement.from_location_id,
            to_location_id=movement.to_location_id,
            receipt_id=movement.receipt_id,
            unit_id=movement.unit_id,
            note=movement.note,
            scan_id=scan_id,
            staff_id=staff_id,
            reverses_id=reverses_id,
            occurred_at=now,
        )

    def movement(self) -> PartMovement:
        return PartMovement(
            part_id=self.part_id,
            reason=self.reason,
            quantity=self.quantity,
            from_location_id=self.from_location_id,
            to_location_id=self.to_location_id,
            receipt_id=self.receipt_id,
            unit_id=self.unit_id,
            note=self.note,
        )


# --- Assembly -------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Take:
    """Parts to take from one location."""

    location_id: UUID
    quantity: int


@dataclass(frozen=True, slots=True)
class PartNeed:
    """One line of the bill of materials, for a number of kits."""

    part_id: UUID
    per_kit: int
    needed: int
    available: int
    takes: tuple[Take, ...]
    """Where the needed parts come from; short if the stock does not suffice."""

    @property
    def missing(self) -> int:
        return max(0, self.needed - self.available)


def plan_takes(*, part_id: UUID, per_kit: int, kits: int, stock: list[PartStock]) -> PartNeed:
    """Where ``kits`` kits get this part from: started boxes first, so they empty.

    ``stock`` holds the part's locations; the order among equal quantities is theirs
    (callers pass them in walking order).
    """
    needed = per_kit * kits
    available = sum(entry.quantity for entry in stock)
    takes: list[Take] = []
    remaining = needed
    for entry in sorted(
        (entry for entry in stock if entry.quantity > 0), key=lambda entry: entry.quantity
    ):
        if remaining == 0:
            break
        quantity = min(remaining, entry.quantity)
        takes.append(Take(location_id=entry.location_id, quantity=quantity))
        remaining -= quantity
    return PartNeed(
        part_id=part_id,
        per_kit=per_kit,
        needed=needed,
        available=available,
        takes=tuple(takes),
    )


def kits_possible(needs: list[PartNeed]) -> int:
    """How many kits the stock suffices for (0 without a bill of materials)."""
    if not needs:
        return 0
    return min(need.available // need.per_kit for need in needs)


def check_kits(kits: int) -> int:
    if not 1 <= kits <= KITS_PER_ASSEMBLY_MAX:
        raise InvalidFieldError(
            "quantity", "out_of_range", f"between 1 and {KITS_PER_ASSEMBLY_MAX}"
        )
    return kits
