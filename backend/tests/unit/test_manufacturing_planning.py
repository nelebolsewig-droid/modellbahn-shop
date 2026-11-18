"""Automatic planning (ADR 0034): what is missing becomes full plates on the emptiest printer."""

from uuid import uuid4

from modellbahn.modules.manufacturing.domain.model import PrinterStatus, Technology
from modellbahn.modules.manufacturing.domain.planning import plan_plates, shortfall
from tests.unit.test_manufacturing_domain import part, printer


class TestShortfall:
    def test_parts_at_hand_and_on_plates_count_against_the_need(self) -> None:
        roof, chimney, door = uuid4(), uuid4(), uuid4()
        missing = shortfall(
            {roof: 4, chimney: 8, door: 2},
            supply={roof: 1, chimney: 8},
            on_plates={roof: 1, door: 5},
        )
        assert missing == {roof: 2}


class TestPlanPlates:
    def test_full_plates_then_the_rest(self) -> None:
        roof = part(per_plate=4)
        d01 = printer(code="d01")
        plan = plan_plates([(roof, 10)], [d01], {})
        assert [plate.quantity for plate in plan.plates] == [4, 4, 2]
        assert plan.unplaced == {}

    def test_the_shortest_queue_gets_the_next_plate(self) -> None:
        roof = part(per_plate=2, plate_minutes=120)
        busy, idle = printer(code="d01"), printer(code="d02")
        plan = plan_plates([(roof, 6)], [busy, idle], {busy.id: 300})
        assert [plate.printer.code for plate in plan.plates] == ["D02", "D02", "D02"]
        plan = plan_plates([(roof, 6)], [busy, idle], {busy.id: 100})
        assert [plate.printer.code for plate in plan.plates] == ["D02", "D01", "D02"]

    def test_only_printers_in_service_of_the_parts_technology(self) -> None:
        resin, filament = part(), part("STW-ALT-ZAUN-H0", technology=Technology.FDM)
        saturn = printer(code="d01")
        broken = printer(code="d02")
        broken.status = PrinterStatus.DEFECTIVE
        plan = plan_plates([(resin, 1), (filament, 3)], [saturn, broken], {})
        assert [(plate.printer.code, plate.part.part_number) for plate in plan.plates] == [
            ("D01", "STW-ALT-DACH-H0")
        ]
        assert plan.unplaced == {filament.id: 3}
