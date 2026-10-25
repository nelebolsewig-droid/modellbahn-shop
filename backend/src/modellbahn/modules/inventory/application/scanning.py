"""The central scan command: what a scan means in its mode, booked at most once.

The device gives every scan its own id. A scan that arrives again (the phone lost its
connection and retries) gets the answer it got the first time, without a second
booking. Every scan is kept with its answer, the rejected ones too.

* **Put away** (*Einlagern*): scan the location, then any number of units. A labelled
  unit is stored there, a stored one moves there. A unit that becomes free goes to the
  order that has waited longest for its variant.
* **Pick** (*Kommissionieren*): for one paid order. A reserved unit of the order is
  picked; any free unit of an article the order still lacks is taken instead of the
  reserved one (that one goes back to free stock). A wrong article is rejected.
* **Look up** (*Auskunft*): show what a code is, book nothing.

A booking scan can be undone for ten minutes, as long as its units have not moved on:
the movements are booked backwards, the journal keeps both.
"""

from dataclasses import dataclass
from typing import Final
from uuid import UUID

from modellbahn.modules.inventory.application.allocation import (
    Allocator,
    PickItem,
    PickList,
    PieceState,
    load_pick_list,
)
from modellbahn.modules.inventory.application.common import Journal, UnitOfWorkFactory
from modellbahn.modules.inventory.application.ports import InventoryUnitOfWork
from modellbahn.modules.inventory.application.units import unit_views
from modellbahn.modules.inventory.domain.errors import (
    InvalidUnitStateError,
    ScanIdReusedError,
    ScanNotFoundError,
    ScanNotUndoableError,
)
from modellbahn.modules.inventory.domain.model import (
    GONE,
    Location,
    Movement,
    Scan,
    ScanMode,
    ScanOutcome,
    Unit,
    UnitStatus,
)
from modellbahn.modules.inventory.domain.scanning import CodeKind, Reading, interpretations
from modellbahn.modules.sales.contracts.orders import OrderStatus
from modellbahn.platform.clock import Clock
from modellbahn.platform.events import JsonObject, JsonValue
from modellbahn.platform.uow import UniqueViolationError

LOCATION_CONTEXT: Final = "location_code"
ORDER_CONTEXT: Final = "order_id"
SCAN_SOURCES: Final = frozenset({"camera", "scanner", "keyboard"})


@dataclass(frozen=True, slots=True)
class ScanRequest:
    scan_id: UUID
    raw: str
    mode: ScanMode
    source: str
    context: dict[str, str]
    """``location_code`` when putting away, ``order_id`` when picking."""


@dataclass(slots=True)
class _Answer:
    """The answer under construction; :meth:`to_json` is what the client gets and replays."""

    outcome: ScanOutcome
    message: str
    resolved: Reading | None = None
    unit: JsonObject | None = None
    location: JsonObject | None = None
    variant: JsonObject | None = None
    effect: JsonObject | None = None
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
            "outcome": self.outcome.value,
            "message": self.message,
            "resolved": resolved,
            "unit": self.unit,
            "location": self.location,
            "variant": self.variant,
            "effect": self.effect,
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
            )
            uow.scans.add(scan)
            # The journal entries refer to the scan.
            await uow.flush()
            journal = Journal(uow, staff_id=staff_id, now=now, scan_id=scan.id)
            answer = await _Interpreter(uow, journal, request).run()
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
        if not scan.matches(mode=request.mode, raw=request.raw, context=request.context):
            raise ScanIdReusedError
        return _with_undo_state(
            scan, dict(scan.response), can_undo=scan.can_undo(self._clock.now())
        )

    async def undo(self, scan_id: UUID, *, staff_id: UUID) -> JsonObject:
        """Book the scan's movements backwards; the journal keeps both directions."""
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
            for entry in reversed(await uow.ledger.for_scan(scan.id)):
                unit = await uow.units.get(entry.unit_id, for_update=True)
                if unit is None:  # pragma: no cover - units are never deleted
                    raise ScanNotUndoableError("changed_since")
                try:
                    movement = unit.revert(entry.movement(), now)
                except InvalidUnitStateError as exc:
                    raise ScanNotUndoableError("changed_since") from exc
                await journal.book(unit, movement, reverses=entry)
            scan.mark_undone(now)
            await uow.commit()
            return _with_undo_state(scan, dict(scan.response), can_undo=False)


def _put_away_refusal(unit: Unit, location: Location) -> str | None:
    """Why ``unit`` cannot go into ``location``, if it cannot."""
    if unit.status in GONE:
        return "unit_gone"
    if unit.status is UnitStatus.PICKED:
        return "unit_picked"
    if not location.holds_goods:
        return "holds_no_goods"
    if unit.location_id == location.id:
        return "already_there"
    return None


class _Interpreter:
    """Decides what one scan means and books it, inside the scan's unit of work."""

    def __init__(self, uow: InventoryUnitOfWork, journal: Journal, request: ScanRequest) -> None:
        self._uow = uow
        self._journal = journal
        self._request = request
        self._now = journal.now

    async def run(self) -> _Answer:
        readings = interpretations(self._request.raw)
        if not readings:
            return _Answer(ScanOutcome.UNKNOWN, "unknown_code")
        locking = self._request.mode is not ScanMode.LOOKUP
        for reading in readings:
            if reading.kind is CodeKind.UNIT:
                unit = await self._uow.units.get_by_code(reading.code, for_update=locking)
                if unit is not None:
                    return await self._on_unit(reading, unit)
            elif reading.kind is CodeKind.LOCATION:
                location = await self._uow.locations.get_by_code(reading.code)
                if location is not None:
                    return await self._on_location(reading, location)
            else:
                variant = await self._uow.catalog.variant_by_gtin(reading.code)
                if variant is not None:
                    return await self._on_variant(reading, variant.variant_id)
        return _Answer(ScanOutcome.UNKNOWN, "not_found", resolved=readings[0])

    # --- What was scanned -----------------------------------------------------------

    async def _on_unit(self, reading: Reading, unit: Unit) -> _Answer:
        match self._request.mode:
            case ScanMode.PUT_AWAY:
                answer = await self._put_away(unit)
            case ScanMode.PICK:
                answer = await self._pick(unit)
            case ScanMode.LOOKUP:
                answer = _Answer(ScanOutcome.INFO, "unit")
        answer.resolved = reading
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
        if not location.holds_goods:
            return _Answer(ScanOutcome.REJECTED, "holds_no_goods", resolved=reading, location=info)
        return _Answer(ScanOutcome.SELECTED, "location_selected", resolved=reading, location=info)

    async def _on_variant(self, reading: Reading, variant_id: UUID) -> _Answer:
        info = await self._variant_info(variant_id)
        if self._request.mode is ScanMode.LOOKUP:
            return _Answer(ScanOutcome.INFO, "variant", resolved=reading, variant=info)
        answer = _Answer(ScanOutcome.REJECTED, "scan_unit_label", resolved=reading, variant=info)
        if self._request.mode is ScanMode.PICK:
            await self._add_progress(answer)
        return answer

    # --- Putting away ---------------------------------------------------------------

    async def _put_away(self, unit: Unit) -> _Answer:
        code = self._request.context.get(LOCATION_CONTEXT)
        if not code:
            return _Answer(ScanOutcome.REJECTED, "location_required")
        location = await self._uow.locations.get_by_code(code.strip().upper())
        if location is None:
            return _Answer(ScanOutcome.REJECTED, "location_unknown")
        refusal = _put_away_refusal(unit, location)
        if refusal is not None:
            return _Answer(
                ScanOutcome.REJECTED, refusal, location=await self._location_info(location)
            )
        self._journal.know(location)
        movement = unit.put_away(location, self._now)
        await self._journal.book(unit, movement)
        effect = await self._effect(movement)
        allocation = await Allocator(self._uow, self._journal).serve_backorder(unit)
        if allocation is not None:
            effect["to_status"] = unit.status.value
            numbers = await self._uow.orders.numbers([allocation.order_id])
            effect["reserved_for"] = numbers.get(allocation.order_id)
        await self._uow.flush()
        return _Answer(
            ScanOutcome.APPLIED,
            movement.reason.value,
            location=await self._location_info(location),
            effect=effect,
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

    async def _pick(self, unit: Unit) -> _Answer:
        pick_list = await self._pick_list()
        if pick_list is None:
            return _Answer(ScanOutcome.REJECTED, "order_unknown")
        if pick_list.order.status is not OrderStatus.PAID or not pick_list.is_allocated:
            return _Answer(ScanOutcome.REJECTED, "order_not_pickable")
        answer = await self._pick_unit(unit, pick_list)
        await self._uow.flush()
        await self._add_progress(answer)
        return answer

    async def _pick_unit(self, unit: Unit, pick_list: PickList) -> _Answer:
        if unit.status in GONE:
            return _Answer(ScanOutcome.REJECTED, "unit_gone")
        own = next(
            (item for item in pick_list.items if item.allocation_id == unit.allocation_id), None
        )
        if own is not None:
            return await self._pick_own(unit, own)
        if unit.allocation_id is not None:
            return _Answer(ScanOutcome.REJECTED, "reserved_for_other_order")
        wanted = [
            item
            for item in pick_list.items
            if item.variant_id == unit.variant_id
            and item.state in {PieceState.BACKORDERED, PieceState.RESERVED}
        ]
        if not wanted:
            known = any(item.variant_id == unit.variant_id for item in pick_list.items)
            return _Answer(ScanOutcome.REJECTED, "variant_complete" if known else "not_in_order")
        if unit.status is not UnitStatus.IN_STOCK:
            return _Answer(ScanOutcome.REJECTED, "unit_not_stored")
        return await self._pick_instead(unit, wanted)

    async def _pick_own(self, unit: Unit, item: PickItem) -> _Answer:
        """A unit reserved for this order: picked, unless it was already."""
        if item.state is not PieceState.RESERVED:
            return _Answer(ScanOutcome.REJECTED, "already_picked")
        movement = unit.pick(self._now)
        await self._journal.book(unit, movement)
        return _Answer(ScanOutcome.APPLIED, "picked", effect=await self._effect(movement))

    async def _pick_instead(self, unit: Unit, wanted: list[PickItem]) -> _Answer:
        """A free unit of a wanted article: it takes a backordered piece, else a reserved one."""
        item = next((i for i in wanted if i.state is PieceState.BACKORDERED), wanted[0])
        released_code: str | None = None
        if item.state is PieceState.RESERVED:
            served = await self._uow.units.serving([item.allocation_id], for_update=True)
            reserved = served.get(item.allocation_id)
            if reserved is not None:
                await self._journal.book(reserved, reserved.release(self._now))
                released_code = reserved.code
        await self._journal.book(unit, unit.allocate(item.allocation_id, self._now))
        movement = unit.pick(self._now)
        await self._journal.book(unit, movement)
        effect = await self._effect(movement)
        effect["released_unit"] = released_code
        return _Answer(ScanOutcome.APPLIED, "picked", effect=effect)

    async def _effect(self, movement: Movement) -> JsonObject:
        return {
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
        return {
            "code": location.code,
            "name": location.name,
            "kind": location.kind.value,
            "holds_goods": location.holds_goods,
            "unit_count": len(units),
        }

    async def _variant_info(self, variant_id: UUID) -> JsonObject:
        variant = (await self._uow.catalog.variants([variant_id]))[variant_id]
        counts = await self._uow.units.counts([variant_id])
        free = sum(count.count for count in counts if count.status is UnitStatus.IN_STOCK)
        return {
            "variant_id": str(variant_id),
            "title": variant.title,
            "sku": variant.sku,
            "free_units": free,
        }
