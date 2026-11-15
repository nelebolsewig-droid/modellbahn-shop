"""The central scan command: what a scan means in its mode, booked at most once.

The device gives every scan its own id. A scan that arrives again (the phone lost its
connection and retries) gets the answer it got the first time, without a second
booking. Every scan is kept with its answer, the rejected ones too.

A label names a model (a variant), never a piece: the variant's EAN-13, and on older
labels a unit code, which stands for its unit's variant. The workshop sticks the same
label on every piece of the model and says how many pieces a scan books (``quantity``);
which units those are, the system decides (ADR 0027).

* **Put away** (*Einlagern*): scan the location, then a model's label: ``quantity``
  pieces of it go into the location, its labelled pieces first (oldest first), then new
  pieces straight into stock. A piece that becomes free goes to the order that has
  waited longest for its variant. A part's label (its part number) puts every part of
  it that waits in receiving into the location (*Wareneingang*).
* **Pick** (*Kommissionieren*): for one paid order. A model's label picks a piece of it
  that is reserved for the order (the scanned one, if an old label named such a piece);
  for a piece still waiting, the oldest free one is taken. A wrong article is rejected.
* **Book out** (*Ausbuchen*): ``quantity`` free pieces of the model leave the stock with
  a reason (sold, unless the context says otherwise): from the chosen location, else
  the oldest anywhere. If fewer are free, nothing is booked.
* **Look up** (*Auskunft*): show what a code is (an old unit code: that piece), book
  nothing.

A booking scan can be undone for ten minutes, as long as its units have not moved on
and its parts are still in the box: the movements are booked backwards, the journals
keep both. Pieces the scan made leave the stock again, as recorded by mistake.

Every scan locks the units it books in one go, by id, as every other path does.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Final
from uuid import UUID

from modellbahn.modules.inventory.application.allocation import (
    Allocator,
    PickItem,
    PickList,
    PieceState,
    load_pick_list,
)
from modellbahn.modules.inventory.application.common import (
    Journal,
    PartJournal,
    UnitOfWorkFactory,
)
from modellbahn.modules.inventory.application.parts import walking_order
from modellbahn.modules.inventory.application.ports import InventoryUnitOfWork
from modellbahn.modules.inventory.application.units import (
    label_new_units,
    put_away,
    unit_views,
)
from modellbahn.modules.inventory.domain.errors import (
    InsufficientPartsError,
    InvalidFieldError,
    InvalidReceiptStateError,
    InvalidUnitStateError,
    ScanIdReusedError,
    ScanNotFoundError,
    ScanNotUndoableError,
)
from modellbahn.modules.inventory.domain.model import (
    SCAN_QUANTITY_MAX,
    LedgerEntry,
    Location,
    Movement,
    MovementReason,
    Scan,
    ScanMode,
    ScanOutcome,
    ScrapReason,
    Unit,
    UnitStatus,
)
from modellbahn.modules.inventory.domain.parts import PartMovementReason
from modellbahn.modules.inventory.domain.scanning import CodeKind, Reading, interpretations
from modellbahn.modules.manufacturing.contracts.parts import PartInfo
from modellbahn.modules.sales.contracts.orders import OrderStatus
from modellbahn.platform.clock import Clock
from modellbahn.platform.events import JsonObject, JsonValue
from modellbahn.platform.uow import UniqueViolationError

LOCATION_CONTEXT: Final = "location_code"
ORDER_CONTEXT: Final = "order_id"
REASON_CONTEXT: Final = "reason"
SCAN_SOURCES: Final = frozenset({"camera", "scanner", "keyboard"})
PART_LOCATIONS_SHOWN: Final = 6
UNDONE_NOTE: Final = "Scan zurückgenommen"
"""The note of a piece a scan made, when the scan is undone (reason: mistake)."""


@dataclass(frozen=True, slots=True)
class ScanRequest:
    scan_id: UUID
    raw: str
    mode: ScanMode
    source: str
    context: dict[str, str]
    """``location_code`` when putting away (and booking out from one location),
    ``order_id`` when picking, ``reason`` (a :class:`ScrapReason`) when booking out."""
    quantity: int = 1
    """Pieces a model's label stands for when putting away or booking out (1 to 200);
    the other modes book one piece, or every part waiting for a box."""


def _check(request: ScanRequest) -> None:
    if not 1 <= request.quantity <= SCAN_QUANTITY_MAX:
        raise InvalidFieldError(
            "quantity", "out_of_range", f"between 1 and {SCAN_QUANTITY_MAX} pieces"
        )
    reason = request.context.get(REASON_CONTEXT)
    if reason is not None and reason not in {member.value for member in ScrapReason}:
        raise InvalidFieldError("context.reason", "invalid", "not a reason for booking out")


@dataclass(slots=True)
class _Answer:
    """The answer under construction; :meth:`to_json` is what the client gets and replays."""

    outcome: ScanOutcome
    message: str
    resolved: Reading | None = None
    unit: JsonObject | None = None
    location: JsonObject | None = None
    variant: JsonObject | None = None
    part: JsonObject | None = None
    effect: JsonObject | None = None
    part_effect: JsonObject | None = None
    stock_effect: JsonObject | None = None
    progress: JsonObject | None = None
    next_expected: JsonObject | None = None

    def to_json(self, scan: Scan) -> JsonObject:
        resolved: JsonValue = (
            {"kind": self.resolved.kind.value, "code": self.resolved.code}
            if self.resolved is not None
            else None
        )
        return {
            "scan_id": str(scan.id),
            "mode": scan.mode.value,
            "quantity": scan.quantity,
            "outcome": self.outcome.value,
            "message": self.message,
            "resolved": resolved,
            "unit": self.unit,
            "location": self.location,
            "variant": self.variant,
            "part": self.part,
            "effect": self.effect,
            "part_effect": self.part_effect,
            "stock_effect": self.stock_effect,
            "progress": self.progress,
            "next_expected": self.next_expected,
        }


def _with_undo_state(scan: Scan, answer: JsonObject, *, can_undo: bool) -> JsonObject:
    return {**answer, "undoable": can_undo, "undone": scan.undone_at is not None}


class ScanService:
    def __init__(self, *, uow_factory: UnitOfWorkFactory, clock: Clock) -> None:
        self._uow = uow_factory
        self._clock = clock

    async def scan(self, request: ScanRequest, *, staff_id: UUID) -> JsonObject:
        """Interpret and book the scan; a repeated scan id gets its first answer again."""
        _check(request)
        try:
            return await self._scan(request, staff_id)
        except UniqueViolationError:
            # The same scan arrived twice at the same moment; the other one booked it.
            return await self._replay(request)

    async def _scan(self, request: ScanRequest, staff_id: UUID) -> JsonObject:
        async with self._uow() as uow:
            existing = await uow.scans.get(request.scan_id)
            if existing is not None:
                return self._repeat(existing, request)
            now = self._clock.now()
            scan = Scan(
                id=request.scan_id,
                staff_id=staff_id,
                mode=request.mode,
                raw=request.raw,
                source=request.source,
                context=dict(request.context),
                outcome=ScanOutcome.UNKNOWN,
                response={},
                created_at=now,
                quantity=request.quantity,
            )
            uow.scans.add(scan)
            # The journal entries refer to the scan.
            await uow.flush()
            journal = Journal(uow, staff_id=staff_id, now=now, scan_id=scan.id)
            part_journal = PartJournal(uow, staff_id=staff_id, now=now, scan_id=scan.id)
            answer = await _Interpreter(uow, journal, part_journal, request).run()
            await part_journal.announce()
            scan.outcome = answer.outcome
            scan.response = answer.to_json(scan)
            await uow.commit()
            return _with_undo_state(scan, scan.response, can_undo=scan.can_undo(now))

    async def _replay(self, request: ScanRequest) -> JsonObject:
        async with self._uow() as uow:
            existing = await uow.scans.get(request.scan_id)
            if existing is None:  # pragma: no cover - the clash means it exists
                raise ScanNotFoundError
            return self._repeat(existing, request)

    def _repeat(self, scan: Scan, request: ScanRequest) -> JsonObject:
        if not scan.matches(
            mode=request.mode,
            raw=request.raw,
            context=request.context,
            quantity=request.quantity,
        ):
            raise ScanIdReusedError
        return _with_undo_state(
            scan, dict(scan.response), can_undo=scan.can_undo(self._clock.now())
        )

    async def undo(self, scan_id: UUID, *, staff_id: UUID) -> JsonObject:
        """Book the scan's movements backwards; the journal keeps both directions.

        A piece the scan made (put away with a quantity, more than lay labelled) cannot
        go back to before its label: it leaves the stock as recorded by mistake, so the
        count is what it was. Pieces booked out are free again where they lay, and the
        order waiting longest for their variant gets them, as with any piece put away.
        """
        async with self._uow() as uow:
            scan = await uow.scans.get(scan_id, for_update=True)
            if scan is None:
                raise ScanNotFoundError
            now = self._clock.now()
            if scan.undone_at is not None:
                raise ScanNotUndoableError("already_undone")
            if not scan.can_undo(now):
                reason = "too_old" if scan.outcome is ScanOutcome.APPLIED else "nothing_booked"
                raise ScanNotUndoableError(reason)
            journal = Journal(uow, staff_id=staff_id, now=now)
            entries = await uow.ledger.for_scan(scan.id)
            units = {unit.id: unit for unit in await uow.units.lock({e.unit_id for e in entries})}
            freed: list[Unit] = []
            for entry in reversed(entries):
                unit = units.get(entry.unit_id)
                if unit is None:  # pragma: no cover - units are never deleted
                    raise ScanNotUndoableError("changed_since")
                if await _booked_since(uow, entry, entries):
                    raise ScanNotUndoableError("changed_since")
                if entry.reason is MovementReason.LABEL:
                    # Made by the scan: it never existed.
                    if not unit.is_in(entry.movement()):
                        raise ScanNotUndoableError("changed_since")
                    await journal.book(unit, unit.scrap(UNDONE_NOTE, now, ScrapReason.MISTAKE))
                    continue
                try:
                    movement = unit.revert(entry.movement(), now)
                except InvalidUnitStateError as exc:
                    raise ScanNotUndoableError("changed_since") from exc
                await journal.book(unit, movement, reverses=entry)
                if entry.reason is MovementReason.SCRAP:
                    freed.append(unit)
            allocator = Allocator(uow, journal)
            for unit in freed:
                await allocator.serve_backorder(unit)
            await _undo_parts(uow, scan, staff_id=staff_id, now=now)
            scan.mark_undone(now)
            await uow.commit()
            return _with_undo_state(scan, dict(scan.response), can_undo=False)


async def _booked_since(
    uow: InventoryUnitOfWork, entry: LedgerEntry, scanned: Sequence[LedgerEntry]
) -> bool:
    """True if something else booked the unit after ``entry``. Moved away and back,
    scrapped and booked in again or corrected, it lies where the scan put it, yet the
    scan is no longer the last word on it. Rows of the scan itself, and their undo rows
    booked a moment ago, do not count."""
    own = {row.id for row in scanned}
    return any(
        row.id is not None
        and entry.id is not None
        and row.id > entry.id
        and row.id not in own
        and row.reverses_id not in own
        for row in await uow.ledger.for_unit(entry.unit_id)
    )


async def _undo_parts(
    uow: InventoryUnitOfWork, scan: Scan, *, staff_id: UUID, now: datetime
) -> None:
    """Take the parts a scan put into a box back out; they wait in receiving again."""
    entries = await uow.part_ledger.for_scan(scan.id)
    if not entries:
        return
    journal = PartJournal(uow, staff_id=staff_id, now=now)
    for entry in reversed(entries):
        if (
            entry.reason is not PartMovementReason.RECEIVE
            or entry.receipt_id is None
            or entry.to_location_id is None
        ):  # pragma: no cover - scans only put parts away
            raise ScanNotUndoableError("changed_since")
        receipt = await uow.receipts.get(entry.receipt_id, for_update=True)
        if receipt is None:  # pragma: no cover - receipts are never deleted
            raise ScanNotUndoableError("changed_since")
        stock = await uow.part_stock.lock(entry.part_id, entry.to_location_id, now=now)
        try:
            movement = receipt.unstore(entry.movement(), stock, now)
        except (InvalidReceiptStateError, InsufficientPartsError) as exc:
            raise ScanNotUndoableError("changed_since") from exc
        journal.book(movement, reverses=entry)
    await journal.announce()


class _Interpreter:
    """Decides what one scan means and books it, inside the scan's unit of work."""

    def __init__(
        self,
        uow: InventoryUnitOfWork,
        journal: Journal,
        part_journal: PartJournal,
        request: ScanRequest,
    ) -> None:
        self._uow = uow
        self._journal = journal
        self._part_journal = part_journal
        self._request = request
        self._now = journal.now
        self._place: Location | None = None
        """The location of the context, once it was found and holds goods."""

    async def run(self) -> _Answer:
        readings = interpretations(self._request.raw)
        if not readings:
            return _Answer(ScanOutcome.UNKNOWN, "unknown_code")
        for reading in readings:
            if reading.kind is CodeKind.UNIT:
                # Not locked: the units a scan books are locked together, by id.
                unit = await self._uow.units.get_by_code(reading.code)
                if unit is not None:
                    return await self._on_unit(reading, unit)
            elif reading.kind is CodeKind.LOCATION:
                location = await self._uow.locations.get_by_code(reading.code)
                if location is not None:
                    return await self._on_location(reading, location)
            elif reading.kind is CodeKind.PART:
                part = await self._uow.manufacturing.part_by_number(reading.code)
                if part is not None:
                    return await self._on_part(reading, part)
            else:
                variant = await self._uow.catalog.variant_by_gtin(reading.code)
                if variant is not None:
                    return await self._on_variant(reading, variant.variant_id)
        return _Answer(ScanOutcome.UNKNOWN, "not_found", resolved=readings[0])

    # --- What was scanned -----------------------------------------------------------

    async def _on_unit(self, reading: Reading, unit: Unit) -> _Answer:
        """An older label with a unit's code: a look-up shows that piece; everywhere
        else it stands for the piece's model, like the EAN beside it."""
        if self._request.mode is not ScanMode.LOOKUP:
            return await self._on_variant(reading, unit.variant_id, scanned=unit)
        answer = _Answer(ScanOutcome.INFO, "unit", resolved=reading)
        answer.unit = await self._unit_info(unit)
        return answer

    async def _on_location(self, reading: Reading, location: Location) -> _Answer:
        info = await self._location_info(location)
        if self._request.mode is ScanMode.LOOKUP:
            return _Answer(ScanOutcome.INFO, "location", resolved=reading, location=info)
        if self._request.mode is ScanMode.PICK:
            answer = _Answer(ScanOutcome.REJECTED, "scan_unit_label", resolved=reading)
            answer.location = info
            await self._add_progress(answer)
            return answer
        # Putting away and booking out: the location of the scans that follow.
        if not location.holds_goods:
            return _Answer(ScanOutcome.REJECTED, "holds_no_goods", resolved=reading, location=info)
        return _Answer(ScanOutcome.SELECTED, "location_selected", resolved=reading, location=info)

    async def _on_variant(
        self, reading: Reading, variant_id: UUID, *, scanned: Unit | None = None
    ) -> _Answer:
        """A model's label: its EAN-13 (the till's barcode), or an older unit code.

        Putting away and booking out take ``quantity`` pieces of it; picking takes the
        piece of it the order is waiting for.
        """
        match self._request.mode:
            case ScanMode.LOOKUP:
                answer = _Answer(ScanOutcome.INFO, "variant")
            case ScanMode.PUT_AWAY:
                answer = await self._book_in(variant_id)
            case ScanMode.PICK:
                answer = await self._pick_variant(variant_id, scanned)
            case ScanMode.SCRAP:
                answer = await self._book_out(variant_id)
        answer.resolved = reading
        answer.variant = await self._variant_info(variant_id)
        return answer

    async def _on_part(self, reading: Reading, part: PartInfo) -> _Answer:
        """A part's label (on the box its parts lie in): parts, not a single piece."""
        match self._request.mode:
            case ScanMode.LOOKUP:
                answer = _Answer(ScanOutcome.INFO, "part")
            case ScanMode.PUT_AWAY:
                answer = await self._store_parts(part)
            case ScanMode.PICK:
                answer = _Answer(ScanOutcome.REJECTED, "scan_unit_label")
                await self._add_progress(answer)
            case ScanMode.SCRAP:
                answer = _Answer(ScanOutcome.REJECTED, "scan_unit_label")
        answer.resolved = reading
        answer.part = await self._part_info(part)
        return answer

    # --- The location of the context ------------------------------------------------

    async def _context_location(self) -> Location | _Answer | None:
        """The location the scans go into (or out of); ``None`` if none is chosen, the
        refusal if it is gone or holds no goods."""
        code = self._request.context.get(LOCATION_CONTEXT, "").strip().upper()
        if not code:
            return None
        location = await self._uow.locations.get_by_code(code)
        if location is None:
            return _Answer(ScanOutcome.REJECTED, "location_unknown")
        if not location.holds_goods:
            return _Answer(
                ScanOutcome.REJECTED,
                "holds_no_goods",
                location=await self._location_info(location),
            )
        self._place = location
        return location

    async def _lock_oldest(
        self, variant_id: UUID, status: UnitStatus, *, limit: int, location: Location | None
    ) -> list[Unit]:
        """Up to ``limit`` units of the variant in ``status`` (lying in ``location``, if
        given), oldest first. They are locked in one go, by id; a unit that changed
        between the first look and the lock is left out."""
        ids = await self._uow.units.oldest(
            variant_id,
            status,
            location_id=location.id if location is not None else None,
            limit=limit,
        )
        locked = [
            unit
            for unit in await self._uow.units.lock(ids)
            if unit.variant_id == variant_id
            and unit.status is status
            and (location is None or unit.location_id == location.id)
        ]
        return sorted(locked, key=lambda unit: (unit.created_at, unit.id))

    async def _pieces_in(self, variant_id: UUID, location: Location) -> int:
        """Pieces of the variant lying in the location (free and reserved)."""
        lying = await self._uow.units.in_locations([location.id])
        return sum(1 for unit in lying if unit.variant_id == variant_id)

    # --- Putting away ---------------------------------------------------------------

    async def _store_parts(self, part: PartInfo) -> _Answer:
        """Every part of it waiting in receiving goes into the chosen location."""
        location = await self._context_location()
        if location is None:
            return _Answer(ScanOutcome.REJECTED, "location_required")
        if isinstance(location, _Answer):
            return location
        receipts = await self._uow.receipts.open(part.part_id, for_update=True)
        if not receipts:
            return _Answer(
                ScanOutcome.REJECTED,
                "no_parts_to_store",
                location=await self._location_info(location),
            )
        stock = await self._uow.part_stock.lock(part.part_id, location.id, now=self._now)
        stored = 0
        for receipt in receipts:
            movement = receipt.store(stock, self._now)
            self._part_journal.book(movement)
            stored += movement.quantity
        jobs = await self._uow.manufacturing.print_jobs({r.print_job_id for r in receipts})
        numbers: list[JsonValue] = [
            jobs[r.print_job_id].number for r in receipts if r.print_job_id in jobs
        ]
        await self._uow.flush()
        return _Answer(
            ScanOutcome.APPLIED,
            "parts_stored",
            location=await self._location_info(location),
            part_effect={
                "quantity": stored,
                "to_location": location.code,
                "in_location": stock.quantity,
                "print_jobs": numbers,
            },
        )

    async def _book_in(self, variant_id: UUID) -> _Answer:
        """``quantity`` pieces of the model into the chosen location: its labelled pieces
        first, oldest first, then new pieces straight into stock. A piece that is free
        then goes to the order that has waited longest for the variant."""
        location = await self._context_location()
        if location is None:
            return _Answer(ScanOutcome.REJECTED, "location_required")
        if isinstance(location, _Answer):
            return location
        wanted = self._request.quantity
        labelled = await self._lock_oldest(
            variant_id, UnitStatus.LABELED, limit=wanted, location=None
        )
        for unit in labelled:
            await put_away(self._uow, self._journal, unit, location)
        made = (
            await label_new_units(
                self._uow,
                self._journal,
                variant_id=variant_id,
                quantity=wanted - len(labelled),
                location=location,
            )
            if len(labelled) < wanted
            else []
        )
        await self._uow.flush()
        booked = [*labelled, *made]
        reserved = [unit for unit in booked if unit.allocation_id is not None]
        allocations = await self._uow.allocations.by_ids(
            {unit.allocation_id for unit in reserved if unit.allocation_id is not None}
        )
        numbers = await self._uow.orders.numbers({a.order_id for a in allocations.values()})
        return _Answer(
            ScanOutcome.APPLIED,
            "booked_in",
            location=await self._location_info(location),
            stock_effect=_stock_effect(
                quantity=len(booked),
                location=location.code,
                in_location=await self._pieces_in(variant_id, location),
                stored=len(labelled),
                created=len(made),
                reserved=len(reserved),
                reserved_for=sorted(set(numbers.values())),
            ),
        )

    # --- Booking out ----------------------------------------------------------------

    async def _book_out(self, variant_id: UUID) -> _Answer:
        """``quantity`` free pieces of the model leave the stock with the context's
        reason: from the chosen location, else the oldest anywhere. All or none."""
        location = await self._context_location()
        if isinstance(location, _Answer):
            return location
        reason = ScrapReason(self._request.context.get(REASON_CONTEXT, ScrapReason.SOLD))
        wanted = self._request.quantity
        free = await self._lock_oldest(
            variant_id, UnitStatus.IN_STOCK, limit=wanted, location=location
        )
        if len(free) < wanted:
            return _Answer(
                ScanOutcome.REJECTED,
                "not_enough_free",
                location=await self._location_info(location) if location else None,
            )
        sources: dict[UUID, int] = {}
        for unit in free:
            if unit.location_id is not None:
                sources[unit.location_id] = sources.get(unit.location_id, 0) + 1
            # Free pieces serve no order: none has to be served again.
            await self._journal.book(unit, unit.scrap("", self._now, reason))
        await self._uow.flush()
        places = await self._uow.locations.by_ids(sources)
        from_locations: list[JsonObject] = [
            {"code": places[place_id].code, "quantity": count}
            for place_id, count in sources.items()
            if place_id in places
        ]
        from_locations.sort(key=lambda source: str(source["code"]))
        return _Answer(
            ScanOutcome.APPLIED,
            "booked_out",
            location=await self._location_info(location) if location else None,
            stock_effect=_stock_effect(
                quantity=len(free),
                location=location.code if location else None,
                in_location=await self._pieces_in(variant_id, location) if location else None,
                reason=reason.value,
                from_locations=from_locations,
            ),
        )

    # --- Picking --------------------------------------------------------------------

    async def _pick_list(self) -> PickList | None:
        raw_id = self._request.context.get(ORDER_CONTEXT, "")
        try:
            order_id = UUID(raw_id)
        except ValueError:
            return None
        order = await self._uow.orders.summary(order_id)
        if order is None:
            return None
        return await load_pick_list(self._uow, order)

    async def _pick_variant(self, variant_id: UUID, scanned: Unit | None) -> _Answer:
        """A piece of the model: one reserved for the order (the scanned one, if an old
        label named such a piece), else a free one for a piece still waiting."""
        pick_list = await self._pick_list()
        if pick_list is None:
            return _Answer(ScanOutcome.REJECTED, "order_unknown")
        if pick_list.order.status is not OrderStatus.PAID or not pick_list.is_allocated:
            return _Answer(ScanOutcome.REJECTED, "order_not_pickable")
        items = [item for item in pick_list.items if item.variant_id == variant_id]
        reserved = [item for item in items if item.state is PieceState.RESERVED]
        own = next(
            (
                item
                for item in reserved
                if scanned is not None and item.allocation_id == scanned.allocation_id
            ),
            reserved[0] if reserved else None,
        )
        backordered = next((i for i in items if i.state is PieceState.BACKORDERED), None)
        if own is not None:
            served = await self._uow.units.serving([own.allocation_id], for_update=True)
            unit = served.get(own.allocation_id)
            answer = (
                await self._pick_own(unit)
                if unit is not None
                else _Answer(ScanOutcome.REJECTED, "variant_not_in_stock")
            )
        elif backordered is not None:
            free = await self._uow.units.oldest_free(variant_id, limit=1)
            answer = (
                await self._pick_free(free[0], backordered)
                if free
                else _Answer(ScanOutcome.REJECTED, "variant_not_in_stock")
            )
        else:
            answer = _Answer(ScanOutcome.REJECTED, "variant_complete" if items else "not_in_order")
        if answer.outcome is ScanOutcome.APPLIED and answer.effect is not None:
            answer.unit = await self._unit_info(
                await self._picked_unit(answer.effect.get("unit_code"))
            )
        await self._uow.flush()
        await self._add_progress(answer)
        return answer

    async def _picked_unit(self, code: object) -> Unit:
        unit = await self._uow.units.get_by_code(str(code))
        if unit is None:  # pragma: no cover - it was just picked
            raise InvalidUnitStateError("the picked unit vanished")
        return unit

    async def _pick_own(self, unit: Unit) -> _Answer:
        """A unit reserved for this order: picked."""
        movement = unit.pick(self._now)
        await self._journal.book(unit, movement)
        return _Answer(ScanOutcome.APPLIED, "picked", effect=await self._effect(movement))

    async def _pick_free(self, unit: Unit, item: PickItem) -> _Answer:
        """A free unit for a piece still waiting: reserved for it and picked at once."""
        await self._journal.book(unit, unit.allocate(item.allocation_id, self._now))
        movement = unit.pick(self._now)
        await self._journal.book(unit, movement)
        return _Answer(ScanOutcome.APPLIED, "picked", effect=await self._effect(movement))

    async def _effect(self, movement: Movement) -> JsonObject:
        unit = await self._uow.units.get(movement.unit_id)
        return {
            "unit_code": unit.code if unit is not None else None,
            "from_status": movement.from_status.value if movement.from_status else None,
            "to_status": movement.to_status.value,
            "from_location": await self._code(movement.from_location_id),
            "to_location": await self._code(movement.to_location_id),
            "reserved_for": None,
            "released_unit": None,
        }

    async def _add_progress(self, answer: _Answer) -> None:
        pick_list = await self._pick_list()
        if pick_list is None:
            return
        answer.progress = {"picked": pick_list.picked, "total": pick_list.total}
        expected = pick_list.next_expected()
        if expected is not None:
            answer.next_expected = {
                "unit_code": expected.unit_code,
                "sku": expected.sku,
                "title": expected.title,
                "location_code": expected.location.code if expected.location else None,
                "location_name": expected.location.name if expected.location else None,
            }

    # --- Information ----------------------------------------------------------------

    async def _code(self, location_id: UUID | None) -> str | None:
        if location_id is None:
            return None
        location = await self._uow.locations.get(location_id)
        return location.code if location is not None else None

    async def _unit_info(self, unit: Unit) -> JsonObject:
        (view,) = await unit_views(self._uow, [unit])
        return {
            "code": unit.code,
            "status": unit.status.value,
            "variant_id": str(unit.variant_id),
            "title": view.variant.title if view.variant else None,
            "sku": view.variant.sku if view.variant else None,
            "location_code": view.location.code if view.location else None,
            "order_id": str(view.order_id) if view.order_id else None,
            "order_number": view.order_number,
        }

    async def _location_info(self, location: Location) -> JsonObject:
        units = await self._uow.units.in_locations([location.id])
        parts = await self._uow.part_stock.in_locations([location.id])
        return {
            "code": location.code,
            "name": location.name,
            "kind": location.kind.value,
            "holds_goods": location.holds_goods,
            "unit_count": len(units),
            "part_count": sum(entry.quantity for entry in parts),
        }

    async def _part_info(self, part: PartInfo) -> JsonObject:
        stock = await self._uow.part_stock.for_parts([part.part_id])
        locations = await self._uow.locations.by_ids({entry.location_id for entry in stock})
        receipts = await self._uow.receipts.open(part.part_id)
        placed = [entry for entry in walking_order(stock, locations) if entry.quantity > 0]
        return {
            "part_id": str(part.part_id),
            "part_number": part.part_number,
            "name": part.name,
            "scale_code": part.scale_code,
            "total": sum(entry.quantity for entry in placed),
            "incoming": sum(receipt.open for receipt in receipts),
            "locations": [
                {"code": locations[entry.location_id].code, "quantity": entry.quantity}
                for entry in placed[:PART_LOCATIONS_SHOWN]
                if entry.location_id in locations
            ],
        }

    async def _variant_info(self, variant_id: UUID) -> JsonObject:
        variant = (await self._uow.catalog.variants([variant_id]))[variant_id]
        counts = await self._uow.units.counts([variant_id])
        free = sum(count.count for count in counts if count.status is UnitStatus.IN_STOCK)
        here: JsonValue = None
        if self._place is not None:
            lying = await self._uow.units.in_locations([self._place.id])
            here = sum(1 for unit in lying if unit.variant_id == variant_id and unit.is_free)
        return {
            "variant_id": str(variant_id),
            "title": variant.title,
            "sku": variant.sku,
            "free_units": free,
            "free_here": here,
        }


def _stock_effect(
    *,
    quantity: int,
    location: str | None,
    in_location: int | None,
    stored: int = 0,
    created: int = 0,
    reserved: int = 0,
    reserved_for: Sequence[str] = (),
    reason: str | None = None,
    from_locations: Sequence[JsonObject] = (),
) -> JsonObject:
    """What a scan of a model's label booked in or out, for the answer."""
    orders: list[JsonValue] = [*reserved_for]
    sources: list[JsonValue] = [*from_locations]
    return {
        "quantity": quantity,
        "location": location,
        "in_location": in_location,
        "stored": stored,
        "created": created,
        "reserved": reserved,
        "reserved_for": orders,
        "reason": reason,
        "from_locations": sources,
    }
