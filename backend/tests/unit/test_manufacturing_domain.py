"""The manufacturing model without a database: printers, parts, kits, plates."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest

from modellbahn.modules.manufacturing.domain.errors import (
    InvalidFieldError,
    InvalidPrintJobStateError,
    PrinterUnavailableError,
)
from modellbahn.modules.manufacturing.domain.events import (
    PrinterStatusChanged,
    PrintJobChanged,
    PrintJobCompleted,
    PrintJobFailed,
)
from modellbahn.modules.manufacturing.domain.model import (
    BillOfMaterials,
    Material,
    Part,
    PartDetails,
    Printer,
    PrinterDetails,
    PrinterStatus,
    PrintJob,
    PrintJobStatus,
    Technology,
    estimate_minutes,
)

NOW = datetime(2026, 10, 29, 8, 0, tzinfo=UTC)
LATER = NOW + timedelta(hours=3)


def printer(technology: Technology = Technology.RESIN, code: str = "d03") -> Printer:
    created, _, _ = Printer.create(
        PrinterDetails(code=code, name=" Saturn   links ", model="Saturn 4 Ultra"),
        technology=technology,
        staff_id=None,
        now=NOW,
    )
    return created


def part(
    number: str = "STW-ALT-DACH-H0",
    *,
    scale: str = "H0",
    technology: Technology = Technology.RESIN,
    plate_minutes: int | None = 190,
    per_plate: int = 1,
    material: Material | None = None,
) -> Part:
    return Part.create(
        PartDetails(
            part_number=number,
            name=f"Teil {number}",
            material_id=material.id if material is not None else None,
            plate_minutes=plate_minutes,
            parts_per_plate=per_plate,
        ),
        scale_code=scale,
        technology=technology,
        material=material,
        now=NOW,
    )


def queued(
    on: Printer | None = None, *lines: tuple[Part, int], minutes: int | None = None
) -> PrintJob:
    on = on or printer()
    job, _ = PrintJob.plan(
        number=17,
        printer=on,
        lines=list(lines) or [(part(technology=on.technology), 4)],
        planned_minutes=minutes,
        note="",
        staff_id=None,
        now=NOW,
    )
    return job


class TestPrinter:
    def test_a_new_printer_is_in_service_and_its_history_starts(self) -> None:
        staff = uuid4()
        created, report, event = Printer.create(
            PrinterDetails(code=" d03 ", name=" Saturn   links ", notes=" Ecke \n\n links "),
            technology=Technology.RESIN,
            staff_id=staff,
            now=NOW,
        )
        assert (created.code, created.name, created.notes) == ("D03", "Saturn links", "Ecke\nlinks")
        assert created.status is PrinterStatus.IN_SERVICE
        assert created.status_changed_at == NOW
        assert created.label == "D03 · Saturn links"
        assert (report.from_status, report.to_status, report.staff_id) == (
            None,
            PrinterStatus.IN_SERVICE,
            staff,
        )
        assert isinstance(event, PrinterStatusChanged)
        assert event.public_payload() == {
            "printer_id": str(created.id),
            "code": "D03",
            "status": "in_service",
            "previous_status": None,
        }

    @pytest.mark.parametrize("code", ["", "D-03", "ABCDEFGHI", "D 3"])
    def test_the_code_on_the_label_is_short_letters_and_digits(self, code: str) -> None:
        with pytest.raises(InvalidFieldError) as caught:
            PrinterDetails(code=code).checked()
        assert caught.value.field == "code"

    def test_the_build_volume_is_given_whole_or_not_at_all(self) -> None:
        whole = PrinterDetails(code="D1", build_x_mm=218, build_y_mm=123, build_z_mm=220).checked()
        assert (whole.build_x_mm, whole.build_y_mm, whole.build_z_mm) == (218, 123, 220)
        with pytest.raises(InvalidFieldError) as caught:
            PrinterDetails(code="D1", build_x_mm=218).checked()
        assert caught.value.code == "incomplete"
        with pytest.raises(InvalidFieldError) as caught:
            PrinterDetails(code="D1", build_x_mm=0, build_y_mm=1, build_z_mm=1).checked()
        assert caught.value.field == "build_x_mm"

    def test_a_report_changes_the_state_and_remembers_why(self) -> None:
        subject = printer()
        reported = subject.report(
            PrinterStatus.DEFECTIVE,
            note=" Düse  verstopft ",
            printing=False,
            queued=2,
            staff_id=None,
            now=LATER,
        )
        assert reported is not None
        report, event = reported
        assert (report.from_status, report.to_status, report.note) == (
            PrinterStatus.IN_SERVICE,
            PrinterStatus.DEFECTIVE,
            "Düse verstopft",
        )
        assert subject.status is PrinterStatus.DEFECTIVE
        assert subject.status_changed_at == LATER
        assert event.previous_status == "in_service"

    def test_a_new_note_on_the_same_state_keeps_the_time_it_began(self) -> None:
        subject = printer()
        subject.report(
            PrinterStatus.DEFECTIVE, note="Düse", printing=False, queued=0, staff_id=None, now=NOW
        )
        again = subject.report(
            PrinterStatus.DEFECTIVE,
            note="Ersatzteil bestellt",
            printing=False,
            queued=0,
            staff_id=None,
            now=LATER,
        )
        assert again is not None
        assert subject.status_note == "Ersatzteil bestellt"
        assert subject.status_changed_at == NOW

    def test_the_same_report_twice_changes_nothing(self) -> None:
        subject = printer()
        assert (
            subject.report(
                PrinterStatus.IN_SERVICE,
                note=" ",
                printing=False,
                queued=0,
                staff_id=None,
                now=LATER,
            )
            is None
        )

    @pytest.mark.parametrize("status", [PrinterStatus.IN_REPAIR, PrinterStatus.RETIRED])
    def test_a_printing_printer_can_break_down_but_not_go_to_repair(
        self, status: PrinterStatus
    ) -> None:
        subject = printer()
        with pytest.raises(PrinterUnavailableError) as caught:
            subject.report(status, note="", printing=True, queued=0, staff_id=None, now=LATER)
        assert caught.value.reason == "busy"
        assert subject.report(
            PrinterStatus.DEFECTIVE, note="", printing=True, queued=0, staff_id=None, now=LATER
        )

    def test_a_printer_with_waiting_jobs_is_not_retired(self) -> None:
        with pytest.raises(PrinterUnavailableError) as caught:
            printer().report(
                PrinterStatus.RETIRED, note="", printing=False, queued=1, staff_id=None, now=LATER
            )
        assert caught.value.reason == "has_queue"


class TestPart:
    def test_details_are_normalised(self) -> None:
        checked = PartDetails(
            part_number=" stw-alt-dach-h0 ",
            name=" Dach   Stellwerk ",
            material_per_part=Decimal("3.456"),
        ).checked()
        assert checked.part_number == "STW-ALT-DACH-H0"
        assert checked.name == "Dach Stellwerk"
        assert checked.material_per_part == Decimal("3.46")

    @pytest.mark.parametrize("number", ["", "STW--DACH", "-STW", "STW DACH", "A" * 41])
    def test_part_numbers_are_letters_digits_and_single_hyphens(self, number: str) -> None:
        with pytest.raises(InvalidFieldError) as caught:
            PartDetails(part_number=number, name="Dach").checked()
        assert caught.value.field == "part_number"

    @pytest.mark.parametrize(
        ("change", "field"),
        [
            ({"layer_height_um": 5}, "layer_height_um"),
            ({"plate_minutes": 0}, "plate_minutes"),
            ({"parts_per_plate": 0}, "parts_per_plate"),
            ({"material_per_part": Decimal(0)}, "material_per_part"),
            ({"name": "  "}, "name"),
        ],
    )
    def test_print_data_stays_in_range(self, change: dict[str, object], field: str) -> None:
        values: dict[str, object] = {"part_number": "DACH", "name": "Dach", **change}
        with pytest.raises(InvalidFieldError) as caught:
            PartDetails(**values).checked()  # type: ignore[arg-type]
        assert caught.value.field == field

    def test_the_material_must_be_of_the_parts_technology(self) -> None:
        filament = Material.create(name="PLA grau", technology=Technology.FDM, notes="", now=NOW)
        with pytest.raises(InvalidFieldError) as caught:
            part(technology=Technology.RESIN, material=filament)
        assert (caught.value.field, caught.value.code) == ("material_id", "wrong_technology")

    def test_a_full_plates_time_is_shared_by_its_parts(self) -> None:
        assert part(plate_minutes=120, per_plate=8).minutes_per_part == 15
        assert part(plate_minutes=None).minutes_per_part is None


class TestBillOfMaterials:
    def bom(self) -> BillOfMaterials:
        return BillOfMaterials.start(
            product_scale_id=uuid4(), scale_code="H0", staff_id=None, now=NOW
        )

    def test_lines_are_kept_in_the_order_given(self) -> None:
        bom = self.bom()
        roof, chimney = part("DACH"), part("SCHORNSTEIN")
        bom.replace([(roof, 1), (chimney, 2)], staff_id=None, now=NOW)
        assert [(line.part_id, line.quantity, line.position) for line in bom.lines] == [
            (roof.id, 1, 0),
            (chimney.id, 2, 1),
        ]
        assert bom.part_count == 3

    def test_replacing_keeps_the_line_objects_of_parts_that_stay(self) -> None:
        bom = self.bom()
        roof, chimney = part("DACH"), part("SCHORNSTEIN")
        bom.replace([(roof, 1), (chimney, 2)], staff_id=None, now=NOW)
        kept = bom.lines[1]
        bom.replace([(chimney, 4)], staff_id=None, now=LATER)
        assert bom.lines == [kept]
        assert (kept.quantity, kept.position) == (4, 0)
        assert bom.updated_at == LATER

    def test_only_parts_of_its_scale(self) -> None:
        with pytest.raises(InvalidFieldError) as caught:
            self.bom().replace([(part(scale="N"), 1)], staff_id=None, now=NOW)
        assert (caught.value.field, caught.value.code) == ("lines.0.part_id", "wrong_scale")

    def test_each_part_once_and_a_sensible_quantity(self) -> None:
        roof = part("DACH")
        with pytest.raises(InvalidFieldError) as caught:
            self.bom().replace([(roof, 1), (roof, 2)], staff_id=None, now=NOW)
        assert caught.value.field == "lines.1.part_id"
        with pytest.raises(InvalidFieldError) as caught:
            self.bom().replace([(roof, 0)], staff_id=None, now=NOW)
        assert caught.value.field == "lines.0.quantity"


class TestEstimate:
    def test_on_filament_every_part_adds_its_share(self) -> None:
        body, chimney = (
            part("BODY", technology=Technology.FDM, plate_minutes=240, per_plate=2),
            part("CHIMNEY", technology=Technology.FDM, plate_minutes=60, per_plate=20),
        )
        # 3 bodies at 120 min, 10 chimneys at 3 min.
        assert estimate_minutes(Technology.FDM, [(body, 3), (chimney, 10)]) == 390

    def test_on_resin_the_slowest_part_sets_the_time(self) -> None:
        tall, flat = part("TALL", plate_minutes=300), part("FLAT", plate_minutes=90)
        assert estimate_minutes(Technology.RESIN, [(tall, 2), (flat, 12)]) == 300

    def test_unknown_while_a_part_has_no_plate_time(self) -> None:
        assert estimate_minutes(Technology.RESIN, [(part(plate_minutes=None), 1)]) is None


class TestPrintJob:
    def test_planning_queues_the_plate_and_estimates_its_time(self) -> None:
        on = printer()
        roof = part("DACH", plate_minutes=190)
        job, event = PrintJob.plan(
            number=17,
            printer=on,
            lines=[(roof, 4)],
            planned_minutes=None,
            note=" Rot  ",
            staff_id=None,
            now=NOW,
        )
        assert job.status is PrintJobStatus.QUEUED
        assert (job.planned_minutes, job.note, job.part_count) == (190, "Rot", 4)
        assert isinstance(event, PrintJobChanged)
        assert event.public_payload() == {
            "job_id": str(job.id),
            "number": 17,
            "printer_id": str(on.id),
            "printer_code": "D03",
            "status": "queued",
            "change": "queued",
        }

    def test_the_slicers_time_wins_over_the_estimate(self) -> None:
        assert queued(None, minutes=212).planned_minutes == 212

    def test_only_parts_of_the_printers_technology_and_not_archived(self) -> None:
        on = printer(Technology.RESIN)
        with pytest.raises(InvalidFieldError) as caught:
            queued(on, (part(technology=Technology.FDM), 1))
        assert caught.value.code == "wrong_technology"
        archived = part()
        archived.active = False
        with pytest.raises(InvalidFieldError) as caught:
            queued(on, (archived, 1))
        assert caught.value.code == "archived"

    def test_a_retired_printer_takes_no_new_plates(self) -> None:
        on = printer()
        on.report(PrinterStatus.RETIRED, note="", printing=False, queued=0, staff_id=None, now=NOW)
        with pytest.raises(PrinterUnavailableError) as caught:
            queued(on)
        assert caught.value.reason == "retired"

    def test_starting_needs_a_printer_in_service_and_free(self) -> None:
        on = printer()
        job = queued(on, minutes=60)
        with pytest.raises(PrinterUnavailableError) as caught:
            job.start(on, busy=True, staff_id=None, now=LATER)
        assert caught.value.reason == "busy"
        on.report(
            PrinterStatus.IN_REPAIR, note="", printing=False, queued=1, staff_id=None, now=NOW
        )
        with pytest.raises(PrinterUnavailableError) as caught:
            job.start(on, busy=False, staff_id=None, now=LATER)
        assert caught.value.reason == "not_in_service"

    def test_the_way_of_a_plate_to_done(self) -> None:
        on = printer()
        roof, chimney = part("DACH"), part("SCHORNSTEIN")
        job = queued(on, (roof, 4), (chimney, 8), minutes=200)
        job.start(on, busy=False, staff_id=None, now=NOW)
        assert job.expected_end == NOW + timedelta(minutes=200)
        job.take_off(on, now=LATER)
        assert (job.status, job.printed_at) == (PrintJobStatus.POST_PROCESSING, LATER)
        done = job.complete(on, good={chimney.id: 6}, staff_id=None, now=LATER)
        assert job.status is PrintJobStatus.DONE
        assert [(line.good, line.failed) for line in job.lines] == [(4, 0), (6, 2)]
        assert isinstance(done, PrintJobCompleted)
        assert (done.good_parts, done.failed_parts) == (10, 2)
        assert job.finished_at == LATER

    def test_completing_straight_from_the_printer_marks_it_printed(self) -> None:
        on = printer()
        job = queued(on)
        job.start(on, busy=False, staff_id=None, now=NOW)
        job.complete(on, good={}, staff_id=None, now=LATER)
        assert job.printed_at == LATER

    def test_good_parts_stay_within_the_plate(self) -> None:
        on = printer()
        roof = part("DACH")
        job = queued(on, (roof, 4))
        job.start(on, busy=False, staff_id=None, now=NOW)
        with pytest.raises(InvalidFieldError) as caught:
            job.complete(on, good={roof.id: 5}, staff_id=None, now=LATER)
        assert caught.value.field == "lines.0.good"
        with pytest.raises(InvalidFieldError):
            job.complete(on, good={uuid4(): 1}, staff_id=None, now=LATER)
        assert job.status is PrintJobStatus.PRINTING

    def test_a_failed_plate_loses_every_part(self) -> None:
        on = printer()
        job = queued(on)
        job.start(on, busy=False, staff_id=None, now=NOW)
        failed = job.fail(on, reason=" Haftung ", staff_id=None, now=LATER)
        assert isinstance(failed, PrintJobFailed)
        assert (job.status, job.failure_reason) == (PrintJobStatus.FAILED, "Haftung")
        assert [(line.good, line.failed) for line in job.lines] == [(0, 4)]

    def test_only_a_waiting_job_is_cancelled_or_moved(self) -> None:
        on, other = printer(), printer(code="D04")
        job = queued(on)
        moved = job.reschedule(printer=other, planned_minutes=90, note="", now=LATER)
        assert (job.printer_id, job.planned_minutes, moved.change) == (other.id, 90, "rescheduled")
        job.start(other, busy=False, staff_id=None, now=LATER)
        with pytest.raises(InvalidPrintJobStateError):
            job.cancel(other, staff_id=None, now=LATER)
        with pytest.raises(InvalidPrintJobStateError):
            job.reschedule(printer=on, planned_minutes=None, note="", now=LATER)

    def test_a_job_moves_only_to_a_printer_of_its_technology(self) -> None:
        job = queued(printer(Technology.RESIN))
        with pytest.raises(InvalidFieldError) as caught:
            job.reschedule(
                printer=printer(Technology.FDM, code="F01"),
                planned_minutes=None,
                note="",
                now=LATER,
            )
        assert caught.value.field == "printer_id"
