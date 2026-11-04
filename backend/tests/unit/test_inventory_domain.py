"""The inventory domain without a database: codes, the scan resolver, units, availability."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from modellbahn.modules.inventory.domain.availability import Availability, availability
from modellbahn.modules.inventory.domain.codes import (
    ALPHABET,
    check_character,
    format_unit_code,
    is_valid_ean13,
    is_valid_unit_code,
    new_unit_code,
    normalize_unit_code,
)
from modellbahn.modules.inventory.domain.errors import InvalidFieldError, InvalidUnitStateError
from modellbahn.modules.inventory.domain.model import (
    UNDO_WINDOW_SECONDS,
    Location,
    LocationKind,
    MovementReason,
    Scan,
    ScanMode,
    ScanOutcome,
    Unit,
    UnitStatus,
)
from modellbahn.modules.inventory.domain.scanning import CodeKind, Reading, interpretations

NOW = datetime(2026, 10, 25, 9, 0, tzinfo=UTC)
CODE = "7KQ2X9F4M" + check_character("7KQ2X9F4M")


class TestUnitCodes:
    def test_new_codes_are_valid_and_differ(self) -> None:
        codes = {new_unit_code() for _ in range(200)}
        assert len(codes) == 200
        assert all(is_valid_unit_code(code) and len(code) == 10 for code in codes)
        assert not any(char in code for code in codes for char in "ILOU")

    def test_every_single_wrong_character_is_caught(self) -> None:
        for position in range(10):
            for char in ALPHABET:
                if char != CODE[position]:
                    wrong = CODE[:position] + char + CODE[position + 1 :]
                    assert not is_valid_unit_code(wrong), wrong

    def test_swapping_neighbours_is_caught_almost_always(self) -> None:
        caught = total = 0
        for _ in range(300):
            code = new_unit_code()
            for position in range(9):
                if code[position] != code[position + 1]:
                    swapped = (
                        code[:position] + code[position + 1] + code[position] + code[position + 2 :]
                    )
                    total += 1
                    caught += not is_valid_unit_code(swapped)
        assert caught / total > 0.95

    def test_reading_tolerates_case_separators_and_look_alikes(self) -> None:
        typed = format_unit_code(CODE).lower().replace(" ", "-")
        assert normalize_unit_code(typed) == CODE
        assert normalize_unit_code("o1l-i") == "0111"

    def test_formatting_groups_for_reading_aloud(self) -> None:
        assert format_unit_code("7KQ2X9F4MZ") == "7KQ2 X9F4 MZ"

    def test_ean13_check_digit(self) -> None:
        assert is_valid_ean13("2000000000015")
        assert not is_valid_ean13("2000000000016")
        assert not is_valid_ean13("200000000001")


class TestScanResolver:
    def test_label_urls(self) -> None:
        assert interpretations(f"https://shop.example/u/{CODE}") == [Reading(CodeKind.UNIT, CODE)]
        assert interpretations("https://shop.example/l/r02-f04-b12") == [
            Reading(CodeKind.LOCATION, "R02-F04-B12")
        ]
        assert interpretations(f"/u/{CODE.lower()}") == [Reading(CodeKind.UNIT, CODE)]

    def test_urls_with_broken_codes_name_nothing(self) -> None:
        assert interpretations(f"https://shop.example/u/{CODE[:-1]}X") == []
        assert interpretations("https://shop.example/produkte/stellwerk") == []
        assert interpretations("https://shop.example/") == []

    def test_typed_codes(self) -> None:
        assert interpretations(f"  {format_unit_code(CODE)} ") == [Reading(CodeKind.UNIT, CODE)]
        # Anything shaped like a location could also be a part number; locations come first.
        assert interpretations("r02-f04") == [
            Reading(CodeKind.LOCATION, "R02-F04"),
            Reading(CodeKind.PART, "R02-F04"),
        ]
        assert interpretations("LAGER") == [
            Reading(CodeKind.LOCATION, "LAGER"),
            Reading(CodeKind.PART, "LAGER"),
        ]

    def test_part_numbers_from_the_label_of_a_box(self) -> None:
        assert interpretations("stw-alt-dach-h0") == [
            Reading(CodeKind.LOCATION, "STW-ALT-DACH-H0"),
            Reading(CodeKind.PART, "STW-ALT-DACH-H0"),
        ]
        # Segments longer than a location's are part numbers only.
        assert interpretations("STW-SCHORNSTEIN-H0") == [
            Reading(CodeKind.PART, "STW-SCHORNSTEIN-H0")
        ]
        assert interpretations("A" * 41) == []

    def test_ean13_names_a_variant(self) -> None:
        assert interpretations("2000000000015") == [Reading(CodeKind.VARIANT, "2000000000015")]

    def test_ambiguous_input_offers_both_readings(self) -> None:
        grouped = f"{CODE[:4]}-{CODE[4:8]}-{CODE[8:]}"
        assert interpretations(grouped) == [
            Reading(CodeKind.UNIT, CODE),
            Reading(CodeKind.LOCATION, grouped),
            Reading(CodeKind.PART, grouped),
        ]

    @pytest.mark.parametrize("raw", ["", "   ", "x" * 301, "Hallo Welt", "R02_F04"])
    def test_garbage_names_nothing(self, raw: str) -> None:
        assert interpretations(raw) == []


def _tree() -> tuple[Location, Location, Location, Location]:
    site = Location.create(parent=None, segment="lager", kind=LocationKind.SITE, name="", now=NOW)
    shelf = Location.create(
        parent=site, segment="R02", kind=LocationKind.SHELF, name="Regal 2", now=NOW
    )
    compartment = Location.create(
        parent=shelf, segment="F04", kind=LocationKind.COMPARTMENT, name="", now=NOW
    )
    box = Location.create(
        parent=compartment, segment="B12", kind=LocationKind.BOX, name="", now=NOW
    )
    return site, shelf, compartment, box


class TestLocations:
    def test_codes_and_paths_follow_the_tree(self) -> None:
        site, shelf, compartment, box = _tree()
        assert (site.code, site.path) == ("LAGER", "LAGER")
        assert (shelf.code, shelf.path) == ("R02", "LAGER.R02")
        assert (compartment.code, compartment.path) == ("R02-F04", "LAGER.R02.F04")
        assert (box.code, box.path, box.depth) == ("R02-F04-B12", "LAGER.R02.F04.B12", 3)

    def test_only_compartments_boxes_and_staging_hold_goods(self) -> None:
        site, shelf, compartment, box = _tree()
        staging = Location.create(
            parent=site, segment="PACK", kind=LocationKind.STAGING, name="Packtisch", now=NOW
        )
        assert [loc.holds_goods for loc in (site, shelf, compartment, box, staging)] == [
            False,
            False,
            True,
            True,
            True,
        ]

    @pytest.mark.parametrize(
        ("parent_index", "kind"),
        [
            (None, LocationKind.SHELF),
            (0, LocationKind.SITE),
            (0, LocationKind.COMPARTMENT),
            (3, LocationKind.BOX),
            (1, LocationKind.STAGING),
        ],
    )
    def test_kinds_go_only_where_they_belong(
        self, parent_index: int | None, kind: LocationKind
    ) -> None:
        parent = None if parent_index is None else _tree()[parent_index]
        with pytest.raises(InvalidFieldError) as error:
            Location.create(parent=parent, segment="X1", kind=kind, name="", now=NOW)
        assert error.value.code == "invalid_parent"

    @pytest.mark.parametrize("segment", ["", "ZU-LANG-1", "R 02", "Ä1", "ABCDEFGHI"])
    def test_segments_are_short_letters_and_digits(self, segment: str) -> None:
        site = _tree()[0]
        with pytest.raises(InvalidFieldError):
            Location.create(parent=site, segment=segment, kind=LocationKind.SHELF, name="", now=NOW)

    def test_rename_keeps_the_code(self) -> None:
        shelf = _tree()[1]
        later = NOW + timedelta(minutes=1)
        shelf.rename("  Regal   am Fenster ", later)
        assert (shelf.name, shelf.code, shelf.updated_at) == ("Regal am Fenster", "R02", later)


def _unit() -> Unit:
    unit, _ = Unit.label(variant_id=uuid4(), code=CODE, now=NOW)
    return unit


class TestUnitLifecycle:
    def test_from_label_to_parcel(self) -> None:
        _, _, compartment, box = _tree()
        unit, labelled = Unit.label(variant_id=uuid4(), code=CODE, now=NOW)
        assert (labelled.reason, labelled.from_status, labelled.to_status) == (
            MovementReason.LABEL,
            None,
            UnitStatus.LABELED,
        )
        stored = unit.put_away(box, NOW)
        assert (stored.reason, unit.status, unit.location_id) == (
            MovementReason.PUT_AWAY,
            UnitStatus.IN_STOCK,
            box.id,
        )
        assert unit.is_free
        moved = unit.put_away(compartment, NOW)
        assert (moved.reason, moved.from_location_id, moved.to_location_id) == (
            MovementReason.MOVE,
            box.id,
            compartment.id,
        )
        allocation_id = uuid4()
        unit.allocate(allocation_id, NOW)
        assert (unit.status, unit.allocation_id, unit.location_id) == (
            UnitStatus.ALLOCATED,
            allocation_id,
            compartment.id,
        )
        picked = unit.pick(NOW)
        assert (picked.allocation_id, unit.status, unit.location_id) == (
            allocation_id,
            UnitStatus.PICKED,
            None,
        )
        unit.ship(NOW)
        assert unit.status is UnitStatus.SHIPPED
        with pytest.raises(InvalidUnitStateError):
            unit.scrap("", NOW)

    def test_a_reserved_unit_moves_with_its_reservation(self) -> None:
        _, _, compartment, box = _tree()
        unit = _unit()
        unit.put_away(box, NOW)
        allocation_id = uuid4()
        unit.allocate(allocation_id, NOW)
        unit.put_away(compartment, NOW)
        assert (unit.status, unit.allocation_id) == (UnitStatus.ALLOCATED, allocation_id)

    def test_release_frees_reserved_and_picked_units(self) -> None:
        box = _tree()[3]
        unit = _unit()
        unit.put_away(box, NOW)
        unit.allocate(uuid4(), NOW)
        unit.release(NOW)
        assert (unit.status, unit.location_id, unit.allocation_id) == (
            UnitStatus.IN_STOCK,
            box.id,
            None,
        )
        unit.allocate(uuid4(), NOW)
        unit.pick(NOW)
        unit.release(NOW)
        # In somebody's hands: it has to be put away again.
        assert (unit.status, unit.location_id) == (UnitStatus.LABELED, None)

    def test_goods_go_only_where_goods_are_held(self) -> None:
        _, shelf, _, box = _tree()
        unit = _unit()
        with pytest.raises(InvalidUnitStateError, match="holds no goods"):
            unit.put_away(shelf, NOW)
        unit.put_away(box, NOW)
        with pytest.raises(InvalidUnitStateError, match="already there"):
            unit.put_away(box, NOW)

    @pytest.mark.parametrize("action", ["pick", "ship", "release"])
    def test_steps_cannot_be_skipped(self, action: str) -> None:
        step = getattr(_unit(), action)
        with pytest.raises(InvalidUnitStateError):
            step(NOW)

    def test_only_stored_units_can_be_allocated(self) -> None:
        unit = _unit()
        with pytest.raises(InvalidUnitStateError):
            unit.allocate(uuid4(), NOW)

    def test_scrapping_frees_the_allocation(self) -> None:
        box = _tree()[3]
        unit = _unit()
        unit.put_away(box, NOW)
        allocation_id = uuid4()
        unit.allocate(allocation_id, NOW)
        scrapped = unit.scrap("Dach gebrochen", NOW)
        assert scrapped.allocation_id == allocation_id
        assert (unit.status, unit.location_id, unit.allocation_id, unit.scrap_note) == (
            UnitStatus.SCRAPPED,
            None,
            None,
            "Dach gebrochen",
        )

    def test_revert_books_backwards_while_nothing_happened_since(self) -> None:
        _, _, compartment, box = _tree()
        unit = _unit()
        unit.put_away(box, NOW)
        allocation_id = uuid4()
        unit.allocate(allocation_id, NOW)
        picked = unit.pick(NOW)
        undone = unit.revert(picked, NOW)
        assert undone.reason is MovementReason.UNDO
        assert (unit.status, unit.location_id, unit.allocation_id) == (
            UnitStatus.ALLOCATED,
            box.id,
            allocation_id,
        )
        moved = unit.put_away(compartment, NOW)
        unit.put_away(box, NOW)
        with pytest.raises(InvalidUnitStateError, match="changed since"):
            unit.revert(moved, NOW)


class TestScans:
    def _scan(self, outcome: ScanOutcome) -> Scan:
        return Scan(
            id=uuid4(),
            staff_id=uuid4(),
            mode=ScanMode.PICK,
            raw=CODE,
            source="camera",
            context={"order_id": "x"},
            outcome=outcome,
            response={},
            created_at=NOW,
        )

    def test_a_repeat_is_recognised_by_its_content(self) -> None:
        scan = self._scan(ScanOutcome.APPLIED)
        assert scan.matches(mode=ScanMode.PICK, raw=CODE, context={"order_id": "x"})
        assert not scan.matches(mode=ScanMode.PICK, raw=CODE, context={})
        assert not scan.matches(mode=ScanMode.LOOKUP, raw=CODE, context={"order_id": "x"})

    def test_only_bookings_can_be_undone_and_only_for_a_while(self) -> None:
        scan = self._scan(ScanOutcome.APPLIED)
        assert scan.can_undo(NOW + timedelta(seconds=UNDO_WINDOW_SECONDS))
        assert not scan.can_undo(NOW + timedelta(seconds=UNDO_WINDOW_SECONDS + 1))
        scan.mark_undone(NOW)
        assert not scan.can_undo(NOW)
        assert not self._scan(ScanOutcome.REJECTED).can_undo(NOW)


class TestAvailability:
    @pytest.mark.parametrize(
        ("free", "wanted", "backorder", "expected"),
        [
            (3, 1, False, Availability.IN_STOCK),
            (3, 3, False, Availability.IN_STOCK),
            (1, 3, True, Availability.MADE_TO_ORDER),
            (0, 1, True, Availability.MADE_TO_ORDER),
            (0, 1, False, Availability.UNAVAILABLE),
            (2, 3, False, Availability.UNAVAILABLE),
        ],
    )
    def test_stock_then_backorder_decide(
        self, free: int, wanted: int, backorder: bool, expected: Availability
    ) -> None:
        assert availability(free_units=free, wanted=wanted, allow_backorder=backorder) is expected
