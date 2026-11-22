"""The workshop's automation (ADR 0034).

A paid piece without stock queues its plates by itself, once; the first plate on the
printer tells the customer; every morning the shop gets „Heute dran“.
"""

from datetime import UTC, datetime
from uuid import UUID

import pytest

from modellbahn.modules.catalog.application.services import CatalogService, ProductDetails
from modellbahn.modules.manufacturing.application.automation import NOTE_PREFIX, AutoPlanner
from modellbahn.modules.manufacturing.application.jobs import PrintJobService
from modellbahn.modules.manufacturing.application.parts import BomService, PartService
from modellbahn.modules.manufacturing.application.printers import PrinterService
from modellbahn.modules.manufacturing.domain.model import PrintJobStatus
from modellbahn.modules.media.application.services import MediaService
from modellbahn.modules.sales.application.cart import CartService
from modellbahn.modules.sales.application.checkout import CheckoutService
from modellbahn.modules.sales.application.common import UnitOfWorkFactory as SalesUnitOfWorkFactory
from modellbahn.modules.sales.application.digest import MorningDigest
from modellbahn.modules.sales.application.orders import OrderService
from modellbahn.modules.sales.application.ports import PaymentGateway
from modellbahn.modules.sales.domain.model import Order
from modellbahn.platform.clock import FixedClock
from modellbahn.platform.mail import InMemoryMailer
from modellbahn.platform.whatsapp import InMemoryMessenger
from tests.conftest import PUBLIC_BASE_URL, SHOP_EMAIL, SHOP_NAME, Deliver
from tests.integration.test_manufacturing_service import resin_part, resin_printer
from tests.integration.test_sales_late_backorder import CUSTOMER, by_transfer, deliver_all
from tests.media_support import InMemoryMediaStorage
from tests.sales_support import FakeSumUp, shop_product, variant_id
from tests.support import mails_to

pytestmark = pytest.mark.usefixtures("clean_database")

ROOF = "STW-ALT-DACH-H0"
CHIMNEY = "STW-ALT-SCHORNSTEIN-H0"
MAKING_SUBJECT = "ist in der Werkstatt"


@pytest.fixture
def payment_gateway() -> PaymentGateway:
    return FakeSumUp()


@pytest.fixture
async def product(
    catalog: CatalogService,
    media: MediaService,
    media_storage: InMemoryMediaStorage,
    deliver: Deliver,
) -> ProductDetails:
    return await shop_product(catalog, media, media_storage, deliver)


@pytest.fixture
async def kit(product: ProductDetails, part_service: PartService, bom_service: BomService) -> UUID:
    """The painted H0 piece: one roof and two chimneys."""
    roof = await resin_part(part_service, ROOF)
    chimney = await resin_part(part_service, CHIMNEY)
    (scale,) = product.product.scales
    await bom_service.replace(scale.id, [(roof, 1), (chimney, 2)], staff_id=None)
    return variant_id(product, "H0", "painted")


async def paid_order(
    carts: CartService, checkout: CheckoutService, orders: OrderService, variant: UUID, n: int
) -> Order:
    order = await by_transfer(carts, checkout, variant, n)
    await orders.confirm_bank_transfer(order.id)
    return order


async def open_plates(print_jobs: PrintJobService) -> list[tuple[str, int, str]]:
    view = await print_jobs.latest(statuses=[PrintJobStatus.QUEUED])
    return sorted(
        (view.parts[line.part_id].part_number, line.quantity, job.note)
        for job in view.jobs
        for line in job.lines
    )


class TestAutomaticPlanning:
    async def test_a_paid_piece_without_stock_queues_its_plates_once(
        self,
        carts: CartService,
        checkout: CheckoutService,
        orders: OrderService,
        deliver: Deliver,
        printer_service: PrinterService,
        print_jobs: PrintJobService,
        planner: AutoPlanner,
        kit: UUID,
    ) -> None:
        await resin_printer(printer_service, "D01")
        order = await paid_order(carts, checkout, orders, kit, 2)
        await deliver_all(deliver)

        plates = await open_plates(print_jobs)
        assert [(number, quantity) for number, quantity, _ in plates] == [
            (ROOF, 1),
            (ROOF, 1),
            (CHIMNEY, 1),
            (CHIMNEY, 1),
            (CHIMNEY, 1),
            (CHIMNEY, 1),
        ]
        assert all(note == f"{NOTE_PREFIX} für {order.number}" for _, _, note in plates)
        # Asked again (the hourly run, a retried event): nothing is missing any more.
        assert (await planner.plan_waiting()).plates == 0
        assert len(await open_plates(print_jobs)) == len(plates)

    async def test_without_a_printer_nothing_is_planned_until_one_is_there(
        self,
        carts: CartService,
        checkout: CheckoutService,
        orders: OrderService,
        deliver: Deliver,
        printer_service: PrinterService,
        print_jobs: PrintJobService,
        planner: AutoPlanner,
        kit: UUID,
    ) -> None:
        await paid_order(carts, checkout, orders, kit, 1)
        await deliver_all(deliver)
        assert await open_plates(print_jobs) == []

        await resin_printer(printer_service, "D01")
        result = await planner.plan_waiting()

        assert (result.plates, result.unplaced_parts) == (3, 0)


class TestMakingStarted:
    async def test_the_first_plate_on_the_printer_tells_the_customer_once(
        self,
        carts: CartService,
        checkout: CheckoutService,
        orders: OrderService,
        deliver: Deliver,
        printer_service: PrinterService,
        print_jobs: PrintJobService,
        mailer: InMemoryMailer,
        kit: UUID,
    ) -> None:
        await resin_printer(printer_service, "D01")
        await resin_printer(printer_service, "D02")
        order = await paid_order(carts, checkout, orders, kit, 1)
        await deliver_all(deliver)
        first, second, *_ = (await print_jobs.latest(statuses=[PrintJobStatus.QUEUED])).jobs

        await print_jobs.start(first.id, staff_id=None)
        await deliver_all(deliver)
        await print_jobs.start(second.id, staff_id=None)
        await deliver_all(deliver)

        assert (await orders.get(order.id)).order.making_started_at is not None
        notices = [m for m in mails_to(mailer, CUSTOMER) if MAKING_SUBJECT in m.subject]
        assert len(notices) == 1
        assert "läuft gerade der Drucker für dich" in notices[0].text


class TestMorningDigest:
    @pytest.fixture
    def whatsapp(self) -> InMemoryMessenger:
        return InMemoryMessenger()

    @pytest.fixture
    def digest(
        self,
        sales_uow: SalesUnitOfWorkFactory,
        clock: FixedClock,
        mailer: InMemoryMailer,
        whatsapp: InMemoryMessenger,
    ) -> MorningDigest:
        return MorningDigest(
            uow_factory=sales_uow,
            clock=clock,
            mailer=mailer,
            recipients=(SHOP_EMAIL, "werkstatt@example.com"),
            public_base_url=PUBLIC_BASE_URL,
            shop_name=SHOP_NAME,
            messenger=whatsapp,
        )

    async def test_once_a_morning_with_the_days_work(
        self,
        carts: CartService,
        checkout: CheckoutService,
        orders: OrderService,
        deliver: Deliver,
        clock: FixedClock,
        mailer: InMemoryMailer,
        digest: MorningDigest,
        whatsapp: InMemoryMessenger,
        kit: UUID,
    ) -> None:
        await paid_order(carts, checkout, orders, kit, 2)
        await deliver_all(deliver)
        clock.set(datetime(2026, 10, 23, 4, 30, tzinfo=UTC))  # 6:30 in Germany
        assert await digest.send_if_due() is False

        clock.set(datetime(2026, 10, 23, 5, 10, tzinfo=UTC))  # 7:10
        assert await digest.send_if_due() is True
        assert await digest.send_if_due() is False

        [mail] = [m for m in mails_to(mailer, SHOP_EMAIL) if m.subject.startswith("Heute dran")]
        assert "Freitag, 23.10." in mail.text
        assert "2 Stück für 1 Bestellung" in mail.text
        assert "1 Bestellung ·" in mail.text  # paid yesterday
        [note] = whatsapp.sent
        assert note.startswith(f"*{mail.subject}*")
        assert "In der Werkstatt: 2 Stück für 1 Bestellung" in note
        assert note.endswith("/admin")
        [copy] = [
            m for m in mails_to(mailer, "werkstatt@example.com") if m.subject.startswith("Heute")
        ]
        assert copy.text == mail.text
