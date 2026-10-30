"""The parts store without a database: receipts, boxes, counting and the assembly plan."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from modellbahn.modules.inventory.domain.errors import (
    InsufficientPartsError,
    InvalidFieldError,
    InvalidReceiptStateError,
)
from modellbahn.modules.inventory.domain.parts import (
    KITS_PER_ASSEMBLY_MAX,
    PartLedgerEntry,
    PartMovementReason,
    PartReceipt,
    PartStock,
    check_kits,
    kits_possible,
    plan_takes,
)

NOW = datetime(2026, 10, 30, 9, 0, tzinfo=UTC)
PART = uuid4()
BOX = uuid4()


def _stock(quantity: int = 0, location: UUID = BOX, part: UUID = PART) -> PartStock:
    stock = PartStock.empty(part_id=part, location_id=location, now=NOW)
    stock.quantity = quantity
    return stock


def _receipt(quantity: int = 7) -> PartReceipt:
    return PartReceipt.arrive(print_job_id=uuid4(), part_id=PART, quantity=quantity, now=NOW)


class TestReceipts:
    def test_storing_puts_every_open_part_into_the_box(self) -> None:
        receipt, stock = _receipt(7), _stock(3)
        movement = receipt.store(stock, NOW)
        assert (receipt.open, receipt.stored, stock.quantity) == (0, 7, 10)
        assert movement.reason is PartMovementReason.RECEIVE
        assert (movement.quantity, movement.from_location_id, movement.to_location_id) == (
            7,
            None,
            BOX,
        )
        assert movement.receipt_id == receipt.id

    def test_nothing_open_nothing_to_store(self) -> None:
        receipt = _receipt(2)
        receipt.store(_stock(), NOW)
        with pytest.raises(InvalidReceiptStateError):
            receipt.store(_stock(), NOW)
        with pytest.raises(InvalidReceiptStateError):
            receipt.write_off("", NOW)

    def test_a_receipt_only_fills_boxes_of_its_part(self) -> None:
        with pytest.raises(InvalidReceiptStateError):
            _receipt().store(_stock(part=uuid4()), NOW)

    def test_writing_off_the_rest(self) -> None:
        receipt = _receipt(4)
        movement = receipt.write_off("  auf dem  Weg  zerbrochen ", NOW)
        assert (receipt.open, receipt.written_off) == (0, 4)
        assert (movement.reason, movement.quantity, movement.note) == (
            PartMovementReason.WRITE_OFF,
            4,
            "auf dem Weg zerbrochen",
        )

    def test_undoing_a_store_takes_the_parts_out_again(self) -> None:
        receipt, stock = _receipt(5), _stock(1)
        stored = receipt.store(stock, NOW)
        back = receipt.unstore(stored, stock, NOW)
        assert (receipt.open, stock.quantity) == (5, 1)
        assert (back.reason, back.from_location_id, back.to_location_id) == (
            PartMovementReason.UNDO,
            BOX,
            None,
        )

    def test_an_undo_fails_once_the_parts_are_gone(self) -> None:
        receipt, stock = _receipt(5), _stock()
        stored = receipt.store(stock, NOW)
        stock.take(3, NOW)
        with pytest.raises(InsufficientPartsError):
            receipt.unstore(stored, stock, NOW)
        with pytest.raises(InvalidReceiptStateError):
            receipt.unstore(stored, _stock(9, location=uuid4()), NOW)

    def test_a_plate_yields_at_least_one_part(self) -> None:
        with pytest.raises(InvalidFieldError):
            _receipt(0)


class TestBoxes:
    def test_taking_more_than_lies_there_fails(self) -> None:
        stock = _stock(2)
        with pytest.raises(InsufficientPartsError):
            stock.take(3, NOW)
        assert stock.quantity == 2

    def test_assembly_names_the_unit(self) -> None:
        unit = uuid4()
        movement = _stock(5).assemble(2, unit, NOW)
        assert (movement.reason, movement.unit_id, movement.from_location_id) == (
            PartMovementReason.ASSEMBLE,
            unit,
            BOX,
        )

    def test_counting_books_the_difference(self) -> None:
        stock = _stock(10)
        missing = stock.count(8, "zwei fehlen", NOW)
        assert missing is not None
        assert (missing.quantity, missing.from_location_id, missing.to_location_id) == (
            2,
            BOX,
            None,
        )
        found = stock.count(11, "", NOW)
        assert found is not None
        assert (found.quantity, found.from_location_id, found.to_location_id) == (3, None, BOX)
        assert stock.count(11, "", NOW) is None
        with pytest.raises(InvalidFieldError):
            stock.count(-1, "", NOW)

    def test_journal_entries_keep_the_movement(self) -> None:
        movement = _stock(5).assemble(2, uuid4(), NOW)
        entry = PartLedgerEntry.book(movement, scan_id=None, staff_id=None, now=NOW)
        assert entry.movement() == movement


class TestAssemblyPlan:
    def test_started_boxes_are_emptied_first(self) -> None:
        full, started = _stock(40, location=uuid4()), _stock(3, location=uuid4())
        need = plan_takes(part_id=PART, per_kit=2, kits=3, stock=[full, started])
        assert (need.needed, need.available, need.missing) == (6, 43, 0)
        assert [(take.location_id, take.quantity) for take in need.takes] == [
            (started.location_id, 3),
            (full.location_id, 3),
        ]

    def test_short_stock_shows_what_is_missing(self) -> None:
        need = plan_takes(part_id=PART, per_kit=4, kits=2, stock=[_stock(5)])
        assert (need.needed, need.missing, sum(t.quantity for t in need.takes)) == (8, 3, 5)

    def test_the_scarcest_part_decides_how_many_kits(self) -> None:
        bodies = plan_takes(part_id=uuid4(), per_kit=1, kits=1, stock=[_stock(9)])
        chimneys = plan_takes(part_id=uuid4(), per_kit=2, kits=1, stock=[_stock(7)])
        assert kits_possible([bodies, chimneys]) == 3
        assert kits_possible([]) == 0

    def test_kits_per_assembly(self) -> None:
        assert check_kits(KITS_PER_ASSEMBLY_MAX) == KITS_PER_ASSEMBLY_MAX
        for kits in (0, KITS_PER_ASSEMBLY_MAX + 1):
            with pytest.raises(InvalidFieldError):
                check_kits(kits)
