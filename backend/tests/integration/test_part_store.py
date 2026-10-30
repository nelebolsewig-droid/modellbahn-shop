"""The parts store against PostgreSQL: from a finished plate through a box into a kit."""

from datetime import timedelta
from uuid import UUID

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine

from modellbahn.modules.catalog.application.services import CatalogService, ProductDetails
from modellbahn.modules.identity.application.services import IdentityService
from modellbahn.modules.inventory.application.assembly import AssemblyService
from modellbahn.modules.inventory.application.labels import LabelRequest, LabelService
from modellbahn.modules.inventory.application.locations import LocationService
from modellbahn.modules.inventory.application.parts import PartStoreService
from modellbahn.modules.inventory.application.ports import LabelSheet
from modellbahn.modules.inventory.application.scanning import ScanService
from modellbahn.modules.inventory.application.units import UnitService
from modellbahn.modules.inventory.domain.errors import (
    BillOfMaterialsMissingError,
    InsufficientPartsError,
    InvalidFieldError,
    InvalidReceiptStateError,
    LocationInUseError,
    LocationNotEmptyError,
    PartNotFoundError,
    ScanNotUndoableError,
)
from modellbahn.modules.inventory.domain.model import LocationKind, ScanMode, UnitStatus
from modellbahn.modules.inventory.domain.parts import PartMovementReason
from modellbahn.modules.inventory.infrastructure.labels import ReportLabLabelRenderer
from modellbahn.modules.manufacturing.application.jobs import PrintJobService
from modellbahn.modules.manufacturing.application.parts import BomService, PartService
from modellbahn.modules.manufacturing.application.printers import PrinterService
from modellbahn.modules.manufacturing.domain.errors import PartInUseError
from modellbahn.modules.media.application.services import MediaService
from modellbahn.platform.clock import FixedClock
from modellbahn.platform.outbox import outbox_table
from tests.conftest import Deliver
from tests.integration.test_manufacturing_service import resin_part, resin_printer
from tests.inventory_support import COMPARTMENT, scan, staff_member, store
from tests.media_support import InMemoryMediaStorage
from tests.sales_support import shop_product, variant_id

pytestmark = pytest.mark.usefixtures("clean_database")

ROOF = "STW-ALT-DACH-H0"
CHIMNEY = "STW-ALT-SCHORNSTEIN-H0"


@pytest.fixture
async def staff(identity: IdentityService) -> UUID:
    return await staff_member(identity)


@pytest.fixture
async def product(
    catalog: CatalogService,
    media: MediaService,
    media_storage: InMemoryMediaStorage,
    deliver: Deliver,
) -> ProductDetails:
    return await shop_product(catalog, media, media_storage, deliver)


@pytest.fixture
async def parts(part_service: PartService) -> dict[str, UUID]:
    return {number: await resin_part(part_service, number) for number in (ROOF, CHIMNEY)}


async def finished_plate(
    printers: PrinterService,
    print_jobs: PrintJobService,
    lines: dict[UUID, tuple[int, int]],
    *,
    code: str = "D01",
) -> int:
    """A plate with ``lines`` (part: planned, good) printed and reported done; its number."""
    printer = await resin_printer(printers, code)
    job = await print_jobs.plan(
        printer_id=printer.id,
        lines=[(part_id, planned) for part_id, (planned, _) in lines.items()],
        planned_minutes=60,
        note="",
        staff_id=None,
    )
    await print_jobs.start(job.job.id, staff_id=None)
    await print_jobs.take_off(job.job.id)
    done = await print_jobs.complete(
        job.job.id, good={part_id: good for part_id, (_, good) in lines.items()}, staff_id=None
    )
    return done.job.number


async def box(locations: LocationService, segment: str = "B01") -> str:
    compartment = await store(locations)
    location = await locations.create(
        parent_code=compartment, segment=segment, kind=LocationKind.BOX, name=""
    )
    return location.code


async def events(engine: AsyncEngine, prefix: str) -> list[dict[str, object]]:
    async with engine.connect() as connection:
        rows = await connection.execute(
            select(outbox_table.c.event_type, outbox_table.c.payload)
            .where(outbox_table.c.event_type.like(f"{prefix}%"))
            .order_by(outbox_table.c.id)
        )
        return [{"type": row.event_type, **row.payload} for row in rows]


class TestReceiving:
    async def test_the_good_parts_of_a_finished_plate_arrive_once(
        self,
        printer_service: PrinterService,
        print_jobs: PrintJobService,
        part_store: PartStoreService,
        parts: dict[str, UUID],
        deliver: Deliver,
        engine: AsyncEngine,
    ) -> None:
        number = await finished_plate(
            printer_service, print_jobs, {parts[ROOF]: (8, 7), parts[CHIMNEY]: (4, 0)}
        )
        await deliver()

        (receipt,) = await part_store.receiving()
        assert receipt.part is not None
        assert (receipt.part.part_number, receipt.receipt.quantity, receipt.receipt.open) == (
            ROOF,
            7,
            7,
        )
        assert receipt.job is not None
        assert (receipt.job.number, receipt.job.printer_code) == (number, "D01")
        assert await part_store.receive_print_job(receipt.receipt.print_job_id) == 0
        assert len(await part_store.receiving()) == 1
        (arrived,) = await events(engine, "inventory.parts.")
        assert (arrived["number"], arrived["parts"]) == (number, 7)

        (line,) = await part_store.overview()
        assert (line.part.part_number, line.total, line.incoming, line.locations) == (
            ROOF,
            0,
            7,
            [],
        )

    async def test_scanning_a_box_and_then_the_part_label_puts_the_parts_away(
        self,
        printer_service: PrinterService,
        print_jobs: PrintJobService,
        part_store: PartStoreService,
        scans: ScanService,
        locations: LocationService,
        parts: dict[str, UUID],
        staff: UUID,
        deliver: Deliver,
        engine: AsyncEngine,
    ) -> None:
        first = await finished_plate(printer_service, print_jobs, {parts[ROOF]: (8, 7)})
        second = await finished_plate(
            printer_service, print_jobs, {parts[ROOF]: (4, 4)}, code="D02"
        )
        await deliver()
        code = await box(locations)

        selected = await scan(scans, staff, code, ScanMode.PUT_AWAY)
        assert selected["outcome"] == "selected"
        answer = await scan(
            scans, staff, ROOF.lower(), ScanMode.PUT_AWAY, context={"location_code": code}
        )

        assert (answer["outcome"], answer["message"]) == ("applied", "parts_stored")
        assert answer["part_effect"] == {
            "quantity": 11,
            "to_location": code,
            "in_location": 11,
            "print_jobs": [first, second],
        }
        assert answer["part"] is not None
        assert answer["undoable"] is True
        assert await part_store.receiving() == []
        (line,) = await part_store.overview()
        assert [(place.location.code, place.quantity) for place in line.locations] == [(code, 11)]
        moved = await events(engine, "inventory.part_stock.")
        assert [(e["reason"], e["quantity"], e["location_code"]) for e in moved] == [
            ("receive", 11, code)
        ]

        again = await scan(scans, staff, ROOF, ScanMode.PUT_AWAY, context={"location_code": code})
        assert (again["outcome"], again["message"]) == ("rejected", "no_parts_to_store")

    async def test_undoing_the_scan_puts_the_parts_back_into_receiving(
        self,
        printer_service: PrinterService,
        print_jobs: PrintJobService,
        part_store: PartStoreService,
        scans: ScanService,
        locations: LocationService,
        parts: dict[str, UUID],
        staff: UUID,
        deliver: Deliver,
    ) -> None:
        await finished_plate(printer_service, print_jobs, {parts[ROOF]: (6, 6)})
        await deliver()
        code = await box(locations)
        answer = await scan(scans, staff, ROOF, ScanMode.PUT_AWAY, context={"location_code": code})

        undone = await scans.undo(UUID(str(answer["scan_id"])), staff_id=staff)

        assert undone["undone"] is True
        (receipt,) = await part_store.receiving()
        assert receipt.receipt.open == 6
        details = await part_store.details(ROOF)
        assert details.line.total == 0
        assert [entry.entry.reason for entry in details.history] == [
            PartMovementReason.UNDO,
            PartMovementReason.RECEIVE,
        ]

    async def test_an_undo_waits_for_parts_still_in_the_box(
        self,
        printer_service: PrinterService,
        print_jobs: PrintJobService,
        part_store: PartStoreService,
        scans: ScanService,
        locations: LocationService,
        parts: dict[str, UUID],
        staff: UUID,
        deliver: Deliver,
    ) -> None:
        await finished_plate(printer_service, print_jobs, {parts[ROOF]: (6, 6)})
        await deliver()
        code = await box(locations)
        answer = await scan(scans, staff, ROOF, ScanMode.PUT_AWAY, context={"location_code": code})
        await part_store.count(ROOF, location_code=code, quantity=2, note="", staff_id=staff)

        with pytest.raises(ScanNotUndoableError) as caught:
            await scans.undo(UUID(str(answer["scan_id"])), staff_id=staff)
        assert caught.value.reason == "changed_since"

    async def test_parts_need_a_place_and_are_only_looked_up_elsewhere(
        self,
        scans: ScanService,
        locations: LocationService,
        parts: dict[str, UUID],
        staff: UUID,
    ) -> None:
        await store(locations)
        no_place = await scan(scans, staff, ROOF, ScanMode.PUT_AWAY)
        assert (no_place["outcome"], no_place["message"]) == ("rejected", "location_required")
        site = await scan(scans, staff, ROOF, ScanMode.PUT_AWAY, context={"location_code": "R01"})
        assert site["message"] == "holds_no_goods"
        nothing = await scan(
            scans, staff, ROOF, ScanMode.PUT_AWAY, context={"location_code": COMPARTMENT}
        )
        assert nothing["message"] == "no_parts_to_store"
        looked_up = await scan(scans, staff, CHIMNEY, ScanMode.LOOKUP)
        assert (looked_up["outcome"], looked_up["message"]) == ("info", "part")
        assert looked_up["resolved"] == {"kind": "part", "code": CHIMNEY}
        picking = await scan(scans, staff, CHIMNEY, ScanMode.PICK)
        assert picking["message"] == "scan_unit_label"

    async def test_what_never_reaches_a_shelf_is_written_off(
        self,
        printer_service: PrinterService,
        print_jobs: PrintJobService,
        part_store: PartStoreService,
        parts: dict[str, UUID],
        staff: UUID,
        deliver: Deliver,
    ) -> None:
        await finished_plate(printer_service, print_jobs, {parts[ROOF]: (3, 3)})
        await deliver()
        (receipt,) = await part_store.receiving()

        view = await part_store.write_off(
            receipt.receipt.id, note="beim Waschen zerbrochen", staff_id=staff
        )

        assert (view.receipt.open, view.receipt.written_off) == (0, 3)
        assert await part_store.receiving() == []
        with pytest.raises(InvalidReceiptStateError):
            await part_store.write_off(receipt.receipt.id, note="", staff_id=staff)
        (entry,) = (await part_store.details(ROOF)).history
        assert (entry.entry.reason, entry.entry.note, entry.staff_name) == (
            PartMovementReason.WRITE_OFF,
            "beim Waschen zerbrochen",
            "Lagerist",
        )


class TestCounting:
    async def test_counting_a_box_books_the_difference(
        self,
        part_store: PartStoreService,
        locations: LocationService,
        parts: dict[str, UUID],
        staff: UUID,
    ) -> None:
        code = await box(locations)
        await part_store.count(
            CHIMNEY, location_code=code, quantity=12, note="Altbestand", staff_id=staff
        )
        details = await part_store.count(
            CHIMNEY, location_code=code.lower(), quantity=9, note="", staff_id=staff
        )

        assert details.line.total == 9
        assert [(e.entry.quantity, e.from_location, e.to_location) for e in details.history] == [
            (3, details.history[0].from_location, None),
            (12, None, details.history[1].to_location),
        ]
        assert details.history[0].from_location is not None
        assert details.history[0].from_location.code == code
        with pytest.raises(PartNotFoundError):
            await part_store.details("STW-GIBT-ES-NICHT")
        with pytest.raises(InvalidFieldError):
            await part_store.count(ROOF, location_code="R01", quantity=1, note="", staff_id=staff)

    async def test_a_box_with_parts_stays(
        self,
        part_store: PartStoreService,
        locations: LocationService,
        parts: dict[str, UUID],
        staff: UUID,
    ) -> None:
        code = await box(locations)
        await part_store.count(ROOF, location_code=code, quantity=5, note="", staff_id=staff)
        node = next(n for n in await locations.tree() if n.location.code == code)
        assert node.part_count == 5
        contents = await locations.contents(code)
        assert [
            (contents.part_infos[p.part_id].part_number, p.quantity) for p in contents.parts
        ] == [(ROOF, 5)]

        with pytest.raises(LocationNotEmptyError):
            await locations.remove(code)
        await part_store.count(ROOF, location_code=code, quantity=0, note="", staff_id=staff)
        with pytest.raises(LocationInUseError):
            await locations.remove(code)

    async def test_a_part_in_stock_cannot_be_deleted(
        self,
        part_service: PartService,
        part_store: PartStoreService,
        locations: LocationService,
        parts: dict[str, UUID],
        staff: UUID,
    ) -> None:
        code = await box(locations)
        await part_store.count(ROOF, location_code=code, quantity=1, note="", staff_id=staff)
        with pytest.raises(PartInUseError):
            await part_service.delete(parts[ROOF])
        await part_service.delete(parts[CHIMNEY])


class TestAssembly:
    async def _kit(
        self,
        bom_service: BomService,
        product: ProductDetails,
        parts: dict[str, UUID],
    ) -> UUID:
        """The H0 kit: one roof and two chimneys; the painted variant."""
        (scale,) = product.product.scales
        await bom_service.replace(scale.id, [(parts[ROOF], 1), (parts[CHIMNEY], 2)], staff_id=None)
        return variant_id(product, "H0", "painted")

    async def test_the_plan_takes_from_started_boxes_first(
        self,
        bom_service: BomService,
        assembly: AssemblyService,
        part_store: PartStoreService,
        locations: LocationService,
        product: ProductDetails,
        parts: dict[str, UUID],
        staff: UUID,
    ) -> None:
        variant = await self._kit(bom_service, product, parts)
        full, started = await box(locations, "B01"), await box(locations, "B02")
        await part_store.count(ROOF, location_code=full, quantity=3, note="", staff_id=staff)
        await part_store.count(CHIMNEY, location_code=full, quantity=3, note="", staff_id=staff)
        await part_store.count(CHIMNEY, location_code=started, quantity=2, note="", staff_id=staff)

        plan = await assembly.plan(variant, 2)

        assert (plan.ready, plan.possible) == (True, 2)
        roof, chimney = plan.parts
        assert (roof.need.needed, [(t.location.code, t.quantity) for t in roof.takes]) == (
            2,
            [(full, 2)],
        )
        assert [(t.location.code, t.quantity) for t in chimney.takes] == [(full, 2), (started, 2)]
        short = await assembly.plan(variant, 4)
        assert (short.ready, [p.need.missing for p in short.parts]) == (False, [1, 3])

    async def test_assembling_takes_the_parts_and_labels_units_that_know_them(
        self,
        bom_service: BomService,
        assembly: AssemblyService,
        part_store: PartStoreService,
        units: UnitService,
        locations: LocationService,
        product: ProductDetails,
        parts: dict[str, UUID],
        staff: UUID,
        engine: AsyncEngine,
        clock: FixedClock,
    ) -> None:
        variant = await self._kit(bom_service, product, parts)
        full, started = await box(locations, "B01"), await box(locations, "B02")
        await part_store.count(ROOF, location_code=full, quantity=3, note="", staff_id=staff)
        await part_store.count(CHIMNEY, location_code=full, quantity=3, note="", staff_id=staff)
        await part_store.count(CHIMNEY, location_code=started, quantity=2, note="", staff_id=staff)
        clock.advance(timedelta(minutes=5))

        done = await assembly.assemble(variant, 2, location_code=COMPARTMENT, staff_id=staff)

        assert [view.unit.status for view in done.units] == [UnitStatus.IN_STOCK] * 2
        assert (await part_store.details(ROOF)).line.total == 1
        chimneys = await part_store.details(CHIMNEY)
        assert [(p.location.code, p.quantity) for p in chimneys.line.locations] == [(full, 1)]
        first = await units.details(done.units[0].unit.code)
        assert sorted(
            (
                p.part.part_number if p.part else "",
                p.quantity,
                p.location.code if p.location else "",
            )
            for p in first.parts
        ) == sorted([(ROOF, 1, full), (CHIMNEY, 2, started)])
        taken = [
            (e["part_number"], e["quantity"], e["previous_location_code"])
            for e in await events(engine, "inventory.part_stock.")
            if e["reason"] == "assemble"
        ]
        assert sorted(taken) == sorted([(ROOF, 2, full), (CHIMNEY, 2, started), (CHIMNEY, 2, full)])

        with pytest.raises(InsufficientPartsError):
            await assembly.assemble(variant, 2, location_code=None, staff_id=staff)

    async def test_without_a_bill_of_materials_there_is_nothing_to_assemble(
        self, assembly: AssemblyService, product: ProductDetails
    ) -> None:
        with pytest.raises(BillOfMaterialsMissingError):
            await assembly.plan(variant_id(product, "H0", "painted"), 1)


class TestPartLabels:
    async def test_a_part_label_carries_the_part_number(
        self, inventory_uow: object, parts: dict[str, UUID]
    ) -> None:
        service = LabelService(uow_factory=inventory_uow, renderer=ReportLabLabelRenderer())  # type: ignore[arg-type]
        pdf = await service.render(
            LabelRequest(
                unit_codes=[],
                location_codes=[],
                part_numbers=[ROOF.lower()],
                sheet=LabelSheet.A4_70X37,
            )
        )
        assert pdf.startswith(b"%PDF")
        with pytest.raises(InvalidFieldError) as caught:
            await service.render(
                LabelRequest(
                    unit_codes=[],
                    location_codes=[],
                    part_numbers=["GIBT-ES-NICHT"],
                    sheet=LabelSheet.A4_70X37,
                )
            )
        assert caught.value.field == "part_numbers.0"


class TestDatabaseRules:
    async def test_the_journal_knows_the_shape_of_each_movement(
        self, engine: AsyncEngine, parts: dict[str, UUID]
    ) -> None:
        statement = text(
            "INSERT INTO inventory.part_ledger (part_id, reason, quantity, occurred_at) "
            "VALUES (:part, :reason, :quantity, now())"
        )
        for reason, quantity in (("receive", 1), ("assemble", 1), ("count", 1), ("count", 0)):
            async with engine.begin() as connection:
                with pytest.raises(IntegrityError):
                    await connection.execute(
                        statement, {"part": parts[ROOF], "reason": reason, "quantity": quantity}
                    )

    async def test_a_box_never_holds_less_than_nothing(
        self, engine: AsyncEngine, locations: LocationService, parts: dict[str, UUID]
    ) -> None:
        compartment = await store(locations)
        async with engine.begin() as connection:
            location_id = await connection.scalar(
                text("SELECT id FROM inventory.locations WHERE code = :code"),
                {"code": compartment},
            )
        async with engine.begin() as connection:
            with pytest.raises(IntegrityError):
                await connection.execute(
                    text(
                        "INSERT INTO inventory.part_stock (part_id, location_id, quantity, "
                        "updated_at) VALUES (:part, :location, -1, now())"
                    ),
                    {"part": parts[ROOF], "location": location_id},
                )
