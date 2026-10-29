"""Printers, parts, kits and plates against PostgreSQL, and the rules the database keeps."""

from datetime import timedelta
from decimal import Decimal
from uuid import UUID

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine

from modellbahn.modules.catalog.application.services import CatalogService
from modellbahn.modules.catalog.domain.errors import ProductScaleHasBomError
from modellbahn.modules.catalog.domain.model import Dimensions
from modellbahn.modules.identity.application.services import IdentityService
from modellbahn.modules.identity.domain.model import StaffRole
from modellbahn.modules.manufacturing.application.jobs import PrintJobService
from modellbahn.modules.manufacturing.application.parts import (
    BomService,
    MaterialService,
    PartService,
)
from modellbahn.modules.manufacturing.application.printers import PrinterService
from modellbahn.modules.manufacturing.domain.errors import (
    InvalidFieldError,
    InvalidPrintJobStateError,
    MaterialInUseError,
    PartInUseError,
    PrinterInUseError,
    PrinterUnavailableError,
    ProductScaleNotFoundError,
)
from modellbahn.modules.manufacturing.domain.model import (
    PartDetails,
    Printer,
    PrinterDetails,
    PrinterStatus,
    PrintJobStatus,
    Technology,
)
from modellbahn.platform.clock import FixedClock
from modellbahn.platform.outbox import outbox_table

pytestmark = pytest.mark.usefixtures("clean_database")

PASSWORD = "Werkstatt-2026-sicher"


async def staff(identity: IdentityService, email: str = "werkstatt@example.com") -> UUID:
    account = await identity.create_staff(
        email=email, display_name="Werkstatt", role=StaffRole.STAFF, password=PASSWORD
    )
    return account.id


async def resin_printer(
    printers: PrinterService, code: str = "D01", staff_id: UUID | None = None
) -> Printer:
    return await printers.create(
        PrinterDetails(code=code, name="Saturn", model="Elegoo Saturn 4 Ultra"),
        technology=Technology.RESIN,
        staff_id=staff_id,
    )


async def resin_part(
    parts: PartService, number: str = "STW-ALT-DACH-H0", *, scale: str = "H0", minutes: int = 190
) -> UUID:
    entry = await parts.create(
        PartDetails(part_number=number, name=f"Teil {number}", plate_minutes=minutes),
        scale_code=scale,
        technology=Technology.RESIN,
    )
    return entry.part.id


async def kit(catalog: CatalogService, scale: str = "H0") -> UUID:
    """A product offered in ``scale``; the id of that product in the scale."""
    product = await catalog.create_product(name="Stellwerk Altenau")
    details = await catalog.add_scale(
        product.product.id, expected_version=None, scale_code=scale, dimensions=Dimensions()
    )
    (product_scale,) = details.product.scales
    return product_scale.id


async def event_types(engine: AsyncEngine) -> list[str]:
    async with engine.connect() as connection:
        rows = await connection.execute(
            select(outbox_table.c.event_type)
            .where(outbox_table.c.event_type.like("manufacturing.%"))
            .order_by(outbox_table.c.id)
        )
        return list(rows.scalars())


class TestPrinters:
    async def test_a_new_printer_stands_in_the_hall_with_its_history(
        self, printer_service: PrinterService, identity: IdentityService
    ) -> None:
        staff_id = await staff(identity)
        printer = await resin_printer(printer_service, staff_id=staff_id)

        hall = await printer_service.hall()
        (desk,) = hall.desks
        assert (desk.printer.code, desk.printing, list(desk.queue)) == ("D01", None, [])
        record = await printer_service.record(printer.id)
        (report,) = record.history
        assert (report.from_status, report.to_status) == (None, PrinterStatus.IN_SERVICE)
        assert record.names == {staff_id: "Werkstatt"}

    async def test_codes_are_unique(self, printer_service: PrinterService) -> None:
        await resin_printer(printer_service, "D01")
        other = await resin_printer(printer_service, "D02")
        with pytest.raises(InvalidFieldError) as caught:
            await resin_printer(printer_service, "d01")
        assert (caught.value.field, caught.value.code) == ("code", "duplicate")
        with pytest.raises(InvalidFieldError):
            await printer_service.change(other.id, PrinterDetails(code="D01"))
        changed = await printer_service.change(other.id, PrinterDetails(code="D12", name="Mars"))
        assert (changed.code, changed.name) == ("D12", "Mars")

    async def test_the_hall_lists_printers_by_code(self, printer_service: PrinterService) -> None:
        for code in ("D10", "D02", "D01"):
            await resin_printer(printer_service, code)
        hall = await printer_service.hall()
        assert [desk.printer.code for desk in hall.desks] == ["D01", "D02", "D10"]

    async def test_a_defect_fails_the_plate_on_the_printer(
        self,
        printer_service: PrinterService,
        part_service: PartService,
        print_jobs: PrintJobService,
        engine: AsyncEngine,
        clock: FixedClock,
    ) -> None:
        printer = await resin_printer(printer_service)
        part_id = await resin_part(part_service)
        job = (
            await print_jobs.plan(
                printer_id=printer.id,
                lines=[(part_id, 4)],
                planned_minutes=None,
                note="",
                staff_id=None,
            )
        ).job
        await print_jobs.start(job.id, staff_id=None)
        clock.advance(timedelta(hours=1))

        reported = await printer_service.report(
            printer.id, PrinterStatus.DEFECTIVE, note="Folie gerissen", staff_id=None
        )

        assert (reported.status, reported.status_note) == (
            PrinterStatus.DEFECTIVE,
            "Folie gerissen",
        )
        failed = (await print_jobs.get(job.id)).job
        assert failed.status is PrintJobStatus.FAILED
        assert failed.failure_reason == "Drucker defekt: Folie gerissen"
        hall = await printer_service.hall()
        assert hall.desks[0].printing is None
        assert await event_types(engine) == [
            "manufacturing.printer.status_changed",
            "manufacturing.print_job.changed",
            "manufacturing.print_job.changed",
            "manufacturing.printer.status_changed",
            "manufacturing.print_job.failed",
        ]

    async def test_repair_waits_for_the_plate_and_retirement_for_the_queue(
        self,
        printer_service: PrinterService,
        part_service: PartService,
        print_jobs: PrintJobService,
    ) -> None:
        printer = await resin_printer(printer_service)
        part_id = await resin_part(part_service)
        plan = {"lines": [(part_id, 1)], "planned_minutes": 60, "note": "", "staff_id": None}
        first = (await print_jobs.plan(printer_id=printer.id, **plan)).job  # type: ignore[arg-type]
        await print_jobs.plan(printer_id=printer.id, **plan)  # type: ignore[arg-type]
        await print_jobs.start(first.id, staff_id=None)

        with pytest.raises(PrinterUnavailableError) as caught:
            await printer_service.report(
                printer.id, PrinterStatus.IN_REPAIR, note="", staff_id=None
            )
        assert caught.value.reason == "busy"
        await print_jobs.take_off(first.id)
        with pytest.raises(PrinterUnavailableError) as caught:
            await printer_service.report(printer.id, PrinterStatus.RETIRED, note="", staff_id=None)
        assert caught.value.reason == "has_queue"
        repaired = await printer_service.report(
            printer.id, PrinterStatus.IN_REPAIR, note="Wartung", staff_id=None
        )
        assert repaired.status is PrinterStatus.IN_REPAIR

    async def test_a_printer_with_plates_keeps_its_history(
        self,
        printer_service: PrinterService,
        part_service: PartService,
        print_jobs: PrintJobService,
    ) -> None:
        unused = await resin_printer(printer_service, "D01")
        used = await resin_printer(printer_service, "D02")
        await print_jobs.plan(
            printer_id=used.id,
            lines=[(await resin_part(part_service), 1)],
            planned_minutes=None,
            note="",
            staff_id=None,
        )
        await printer_service.delete(unused.id)
        with pytest.raises(PrinterInUseError):
            await printer_service.delete(used.id)
        assert [desk.printer.code for desk in (await printer_service.hall()).desks] == ["D02"]


class TestMaterialsAndParts:
    async def test_materials_by_technology_with_their_parts(
        self, material_service: MaterialService, part_service: PartService
    ) -> None:
        resin = await material_service.create(
            name="Resin grau", technology=Technology.RESIN, notes=""
        )
        await material_service.create(name="PLA schwarz", technology=Technology.FDM, notes="")
        with pytest.raises(InvalidFieldError) as caught:
            await material_service.create(name="Resin grau", technology=Technology.RESIN, notes="")
        assert caught.value.code == "duplicate"
        await part_service.create(
            PartDetails(part_number="DACH", name="Dach", material_id=resin.material.id),
            scale_code="H0",
            technology=Technology.RESIN,
        )

        entries = await material_service.all()
        assert [(entry.material.name, entry.parts) for entry in entries] == [
            ("PLA schwarz", 0),
            ("Resin grau", 1),
        ]
        with pytest.raises(MaterialInUseError):
            await material_service.delete(resin.material.id)
        archived = await material_service.change(
            resin.material.id, name="Resin grau", notes="", active=False
        )
        assert archived.material.active is False

    async def test_a_part_needs_a_known_scale_and_a_material_of_its_technology(
        self, material_service: MaterialService, part_service: PartService
    ) -> None:
        filament = await material_service.create(
            name="PLA grau", technology=Technology.FDM, notes=""
        )
        with pytest.raises(InvalidFieldError) as caught:
            await part_service.create(
                PartDetails(part_number="DACH", name="Dach"),
                scale_code="XX",
                technology=Technology.RESIN,
            )
        assert caught.value.field == "scale_code"
        with pytest.raises(InvalidFieldError) as caught:
            await part_service.create(
                PartDetails(part_number="DACH", name="Dach", material_id=filament.material.id),
                scale_code="H0",
                technology=Technology.RESIN,
            )
        assert caught.value.code == "wrong_technology"

    async def test_parts_are_found_by_scale_and_number(self, part_service: PartService) -> None:
        await resin_part(part_service, "STW-ALT-DACH-H0")
        await resin_part(part_service, "STW-ALT-DACH-N", scale="N")
        archived = await resin_part(part_service, "STW-ALT-FENSTER-H0")
        entry = await part_service.change(
            archived,
            PartDetails(
                part_number="STW-ALT-FENSTER-H0",
                name="Fenster",
                material_per_part=Decimal("1.5"),
            ),
            active=False,
        )
        assert (entry.part.active, entry.part.material_per_part) == (False, Decimal("1.50"))

        def numbers(entries: list) -> list[str]:  # type: ignore[type-arg]
            return [entry.part.part_number for entry in entries]

        assert numbers(await part_service.search()) == ["STW-ALT-DACH-H0", "STW-ALT-DACH-N"]
        assert numbers(await part_service.search(scale_code="N")) == ["STW-ALT-DACH-N"]
        assert numbers(await part_service.search(query="fenster", include_archived=True)) == [
            "STW-ALT-FENSTER-H0"
        ]
        assert numbers(await part_service.search(query="100%_")) == []

    async def test_part_numbers_are_unique(self, part_service: PartService) -> None:
        await resin_part(part_service, "DACH")
        with pytest.raises(InvalidFieldError) as caught:
            await resin_part(part_service, "dach")
        assert (caught.value.field, caught.value.code) == ("part_number", "duplicate")

    async def test_a_part_in_use_stays(
        self,
        part_service: PartService,
        bom_service: BomService,
        catalog: CatalogService,
    ) -> None:
        unused = await resin_part(part_service, "LOSE")
        needed = await resin_part(part_service, "DACH")
        product_scale_id = await kit(catalog)
        await bom_service.replace(product_scale_id, [(needed, 1)], staff_id=None)

        await part_service.delete(unused)
        with pytest.raises(PartInUseError):
            await part_service.delete(needed)
        record = await part_service.record(needed)
        (use,) = record.uses
        assert (use.product_scale.product_name, use.quantity) == ("Stellwerk Altenau", 1)
        assert record.entry.usage.boms == 1

    async def test_a_parts_record_names_the_other_parts_on_its_plates(
        self,
        printer_service: PrinterService,
        part_service: PartService,
        print_jobs: PrintJobService,
    ) -> None:
        printer = await resin_printer(printer_service)
        roof = await resin_part(part_service, "DACH")
        chimney = await resin_part(part_service, "SCHORNSTEIN")
        await print_jobs.plan(
            printer_id=printer.id,
            lines=[(roof, 2), (chimney, 4)],
            planned_minutes=None,
            note="",
            staff_id=None,
        )
        record = await part_service.record(roof)
        (job,) = record.jobs
        assert {record.parts[line.part_id].part_number for line in job.lines} == {
            "DACH",
            "SCHORNSTEIN",
        }


class TestBillsOfMaterials:
    async def test_a_kit_without_parts_has_no_bill_of_materials(
        self, bom_service: BomService, catalog: CatalogService
    ) -> None:
        view = await bom_service.get(await kit(catalog))
        assert (view.bom, view.part_count, view.print_minutes) == (None, 0, None)
        assert view.product_scale.scale_code == "H0"

    async def test_unknown_product_scale(self, bom_service: BomService) -> None:
        with pytest.raises(ProductScaleNotFoundError):
            await bom_service.get(UUID(int=1))

    async def test_set_change_and_remove_the_parts_of_a_kit(
        self,
        bom_service: BomService,
        part_service: PartService,
        catalog: CatalogService,
        identity: IdentityService,
    ) -> None:
        staff_id = await staff(identity)
        product_scale_id = await kit(catalog)
        body = await resin_part(part_service, "BODY", minutes=240)
        roof = await resin_part(part_service, "DACH", minutes=90)

        view = await bom_service.replace(
            product_scale_id, [(body, 1), (roof, 2)], staff_id=staff_id
        )
        assert view.bom is not None
        assert [(line.part_id, line.quantity) for line in view.bom.lines] == [(body, 1), (roof, 2)]
        assert (view.part_count, view.print_minutes) == (3, 420)

        view = await bom_service.replace(product_scale_id, [(roof, 3)], staff_id=staff_id)
        assert view.bom is not None
        assert [(line.part_id, line.quantity) for line in view.bom.lines] == [(roof, 3)]
        again = await bom_service.get(product_scale_id)
        assert again.part_count == 3

        removed = await bom_service.replace(product_scale_id, [], staff_id=staff_id)
        assert removed.bom is None
        assert (await bom_service.get(product_scale_id)).bom is None

    async def test_only_parts_of_the_kits_scale(
        self, bom_service: BomService, part_service: PartService, catalog: CatalogService
    ) -> None:
        n_roof = await resin_part(part_service, "DACH-N", scale="N")
        with pytest.raises(InvalidFieldError) as caught:
            await bom_service.replace(await kit(catalog), [(n_roof, 1)], staff_id=None)
        assert (caught.value.field, caught.value.code) == ("lines.0.part_id", "wrong_scale")
        with pytest.raises(InvalidFieldError) as caught:
            await bom_service.replace(await kit(catalog, "N"), [(UUID(int=7), 1)], staff_id=None)
        assert caught.value.code == "unknown"

    async def test_the_catalogue_keeps_a_scale_with_a_bill_of_materials(
        self, bom_service: BomService, part_service: PartService, catalog: CatalogService
    ) -> None:
        product_scale_id = await kit(catalog)
        await bom_service.replace(
            product_scale_id, [(await resin_part(part_service), 1)], staff_id=None
        )
        with pytest.raises(ProductScaleHasBomError):
            await catalog.remove_scale(product_scale_id, expected_version=None)
        await bom_service.replace(product_scale_id, [], staff_id=None)
        details = await catalog.remove_scale(product_scale_id, expected_version=None)
        assert details.product.scales == []


class TestPrintJobs:
    async def test_the_way_of_a_plate_through_the_hall(
        self,
        printer_service: PrinterService,
        part_service: PartService,
        print_jobs: PrintJobService,
        identity: IdentityService,
        engine: AsyncEngine,
        clock: FixedClock,
    ) -> None:
        staff_id = await staff(identity)
        printer = await resin_printer(printer_service)
        roof = await resin_part(part_service, "DACH", minutes=190)
        chimney = await resin_part(part_service, "SCHORNSTEIN", minutes=60)
        first = (
            await print_jobs.plan(
                printer_id=printer.id,
                lines=[(roof, 4), (chimney, 8)],
                planned_minutes=None,
                note="Ecke links",
                staff_id=staff_id,
            )
        ).job
        second = (
            await print_jobs.plan(
                printer_id=printer.id,
                lines=[(chimney, 20)],
                planned_minutes=75,
                note="",
                staff_id=staff_id,
            )
        ).job
        assert (first.planned_minutes, second.planned_minutes) == (190, 75)
        assert second.number == first.number + 1

        started = (await print_jobs.start(first.id, staff_id=staff_id)).job
        assert started.expected_end == clock.now() + timedelta(minutes=190)
        with pytest.raises(PrinterUnavailableError) as caught:
            await print_jobs.start(second.id, staff_id=staff_id)
        assert caught.value.reason == "busy"
        hall = await printer_service.hall()
        assert hall.desks[0].printing is not None
        assert [job.id for job in hall.desks[0].queue] == [second.id]

        clock.advance(timedelta(minutes=195))
        await print_jobs.take_off(first.id)
        await print_jobs.start(second.id, staff_id=staff_id)
        hall = await printer_service.hall()
        assert [job.id for job in hall.post_processing] == [first.id]
        assert hall.desks[0].printing is not None
        assert hall.desks[0].printing.id == second.id

        done = (await print_jobs.complete(first.id, good={chimney: 7}, staff_id=staff_id)).job
        assert done.status is PrintJobStatus.DONE
        assert [(line.good, line.failed) for line in done.lines] == [(4, 0), (7, 1)]
        with pytest.raises(InvalidPrintJobStateError):
            await print_jobs.cancel(first.id, staff_id=staff_id)

        listed = await print_jobs.latest(statuses=[PrintJobStatus.DONE])
        assert [job.id for job in listed.jobs] == [first.id]
        assert listed.printers[printer.id].code == "D01"
        assert {part.part_number for part in listed.parts.values()} == {"DACH", "SCHORNSTEIN"}
        assert (await event_types(engine))[-1] == "manufacturing.print_job.completed"

    async def test_a_waiting_plate_moves_to_another_printer_or_is_cancelled(
        self,
        printer_service: PrinterService,
        part_service: PartService,
        print_jobs: PrintJobService,
    ) -> None:
        first = await resin_printer(printer_service, "D01")
        second = await resin_printer(printer_service, "D02")
        filament = await printer_service.create(
            PrinterDetails(code="F01"), technology=Technology.FDM, staff_id=None
        )
        job = (
            await print_jobs.plan(
                printer_id=first.id,
                lines=[(await resin_part(part_service), 2)],
                planned_minutes=None,
                note="",
                staff_id=None,
            )
        ).job
        moved = (
            await print_jobs.reschedule(
                job.id, printer_id=second.id, planned_minutes=120, note="eilig"
            )
        ).job
        assert (moved.printer_id, moved.planned_minutes, moved.note) == (second.id, 120, "eilig")
        with pytest.raises(InvalidFieldError) as caught:
            await print_jobs.reschedule(
                job.id, printer_id=filament.id, planned_minutes=None, note=""
            )
        assert caught.value.field == "printer_id"

        cancelled = (await print_jobs.cancel(job.id, staff_id=None)).job
        assert cancelled.status is PrintJobStatus.CANCELLED
        assert (await printer_service.hall()).desks[1].queue == []

    async def test_nothing_starts_on_a_defective_printer(
        self,
        printer_service: PrinterService,
        part_service: PartService,
        print_jobs: PrintJobService,
    ) -> None:
        printer = await resin_printer(printer_service)
        job = (
            await print_jobs.plan(
                printer_id=printer.id,
                lines=[(await resin_part(part_service), 1)],
                planned_minutes=None,
                note="",
                staff_id=None,
            )
        ).job
        await printer_service.report(printer.id, PrinterStatus.DEFECTIVE, note="", staff_id=None)
        with pytest.raises(PrinterUnavailableError) as caught:
            await print_jobs.start(job.id, staff_id=None)
        assert caught.value.reason == "not_in_service"

    async def test_unknown_parts_are_named_by_their_line(
        self, printer_service: PrinterService, print_jobs: PrintJobService
    ) -> None:
        printer = await resin_printer(printer_service)
        with pytest.raises(InvalidFieldError) as caught:
            await print_jobs.plan(
                printer_id=printer.id,
                lines=[(UUID(int=5), 1)],
                planned_minutes=None,
                note="",
                staff_id=None,
            )
        assert (caught.value.field, caught.value.code) == ("lines.0.part_id", "unknown")


class TestDatabaseRules:
    """What the database refuses even if the code let it through."""

    async def setup(
        self,
        printer_service: PrinterService,
        part_service: PartService,
        print_jobs: PrintJobService,
    ) -> tuple[UUID, UUID, UUID]:
        printer = await resin_printer(printer_service)
        part_id = await resin_part(part_service)
        job = (
            await print_jobs.plan(
                printer_id=printer.id,
                lines=[(part_id, 4)],
                planned_minutes=None,
                note="",
                staff_id=None,
            )
        ).job
        return printer.id, part_id, job.id

    async def refused(
        self, engine: AsyncEngine, statement: str, constraint: str, **values: object
    ) -> None:
        with pytest.raises(IntegrityError, match=constraint):
            async with engine.begin() as connection:
                await connection.execute(text(statement), values)

    async def test_two_plates_printing_on_one_printer(
        self,
        printer_service: PrinterService,
        part_service: PartService,
        print_jobs: PrintJobService,
        engine: AsyncEngine,
    ) -> None:
        printer_id, part_id, job_id = await self.setup(printer_service, part_service, print_jobs)
        await print_jobs.start(job_id, staff_id=None)
        second = (
            await print_jobs.plan(
                printer_id=printer_id,
                lines=[(part_id, 1)],
                planned_minutes=None,
                note="",
                staff_id=None,
            )
        ).job
        await self.refused(
            engine,
            "UPDATE manufacturing.print_jobs SET status = 'printing', started_at = now() "
            "WHERE id = :job_id",
            "print_jobs_one_printing_idx",
            job_id=second.id,
        )

    async def test_more_good_parts_than_planned(
        self,
        printer_service: PrinterService,
        part_service: PartService,
        print_jobs: PrintJobService,
        engine: AsyncEngine,
    ) -> None:
        _, _, job_id = await self.setup(printer_service, part_service, print_jobs)
        await self.refused(
            engine,
            "UPDATE manufacturing.print_job_lines SET good = 5 WHERE job_id = :job_id",
            "ck_print_job_lines_counts_within_quantity",
            job_id=job_id,
        )

    async def test_a_part_of_another_technology_on_the_plate(
        self,
        printer_service: PrinterService,
        part_service: PartService,
        print_jobs: PrintJobService,
        engine: AsyncEngine,
    ) -> None:
        _, _, job_id = await self.setup(printer_service, part_service, print_jobs)
        filament = await part_service.create(
            PartDetails(part_number="FDM-TEIL", name="Teil"),
            scale_code="H0",
            technology=Technology.FDM,
        )
        await self.refused(
            engine,
            "INSERT INTO manufacturing.print_job_lines "
            "(job_id, part_id, technology, quantity, position) "
            "VALUES (:job_id, :part_id, 'resin', 1, 1)",
            "fk_print_job_lines_part_id_technology_parts",
            job_id=job_id,
            part_id=filament.part.id,
        )

    async def test_a_part_of_another_scale_in_a_kit(
        self,
        part_service: PartService,
        bom_service: BomService,
        catalog: CatalogService,
        engine: AsyncEngine,
    ) -> None:
        product_scale_id = await kit(catalog)
        await bom_service.replace(
            product_scale_id, [(await resin_part(part_service), 1)], staff_id=None
        )
        n_part = await resin_part(part_service, "DACH-N", scale="N")
        await self.refused(
            engine,
            "INSERT INTO manufacturing.bom_lines "
            "(product_scale_id, part_id, scale_code, quantity, position) "
            "VALUES (:product_scale_id, :part_id, 'H0', 1, 1)",
            "fk_bom_lines_part_id_scale_code_parts",
            product_scale_id=product_scale_id,
            part_id=n_part,
        )
