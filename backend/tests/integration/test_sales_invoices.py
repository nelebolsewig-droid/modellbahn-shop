"""Invoices and corrections against the database (ADR 0038).

Dispatching an order issues its invoice, and the shipping e-mail carries it as a PDF.
Money given back afterwards gets a correction that names the invoice. Numbers run per
series and year without gaps, and the outbox may deliver an event twice.
"""

import asyncio
from collections.abc import Awaitable, Callable
from uuid import UUID, uuid4

import pytest

from modellbahn.modules.catalog.application.services import CatalogService
from modellbahn.modules.identity.application.services import IdentityService
from modellbahn.modules.inventory.application.allocation import AllocationService
from modellbahn.modules.inventory.application.locations import LocationService
from modellbahn.modules.inventory.application.scanning import ScanService
from modellbahn.modules.inventory.application.units import UnitService
from modellbahn.modules.media.application.services import MediaService
from modellbahn.modules.sales.application.cart import CartService
from modellbahn.modules.sales.application.checkout import CheckoutService
from modellbahn.modules.sales.application.common import UnitOfWorkFactory
from modellbahn.modules.sales.application.invoices import InvoiceService
from modellbahn.modules.sales.application.orders import OrderService
from modellbahn.modules.sales.domain.errors import InvoiceNotFoundError, OrderNotFoundError
from modellbahn.modules.sales.domain.events import OrderRefunded
from modellbahn.modules.sales.domain.invoices import ORDER_SOURCE, InvoiceKind
from modellbahn.modules.sales.infrastructure.invoices import ReportLabInvoiceRenderer
from modellbahn.platform.clock import FixedClock
from modellbahn.platform.mail import InMemoryMailer
from tests.conftest import Deliver
from tests.inventory_support import pick_everything, staff_member, stock_up
from tests.media_support import InMemoryMediaStorage
from tests.sales_support import filled_cart, place, shop_product, variant_id
from tests.support import mails_to

CUSTOMER = "erika@example.de"

type ShipOrder = Callable[[], Awaitable[UUID]]


@pytest.fixture
async def painted(
    catalog: CatalogService,
    media: MediaService,
    media_storage: InMemoryMediaStorage,
    deliver: Deliver,
) -> UUID:
    return variant_id(await shop_product(catalog, media, media_storage, deliver), "H0", "painted")


@pytest.fixture
def ship(
    carts: CartService,
    checkout: CheckoutService,
    orders: OrderService,
    deliver: Deliver,
    identity: IdentityService,
    locations: LocationService,
    units: UnitService,
    scans: ScanService,
    allocation: AllocationService,
    painted: UUID,
) -> ShipOrder:
    """Places, pays, picks and ships one order; returns its id."""

    staff: list[UUID] = []

    async def ship_one() -> UUID:
        if not staff:
            staff.append(await staff_member(identity))
        await stock_up(locations, units, painted)
        cart = await filled_cart(carts, (painted, 1))
        order = (await place(checkout, carts, cart)).details.order
        await checkout.pay(
            public_token=order.public_token, method="succeeds", idempotency_key=uuid4()
        )
        await deliver()
        await pick_everything(scans, allocation, order.id, staff[0])
        await orders.ship(order.id, carrier="Hermes", tracking_number="H123")
        return order.id

    return ship_one


def refunded(order_id: UUID, clock: FixedClock, amount_cents: int) -> OrderRefunded:
    return OrderRefunded(
        aggregate_id=order_id,
        occurred_at=clock.now(),
        number="MB-2026-00001",
        total_cents=amount_cents,
        amount_cents=amount_cents,
        refunded_cents=amount_cents,
    )


class TestInvoice:
    async def test_dispatch_issues_the_invoice_and_mails_it(
        self,
        ship: ShipOrder,
        invoices: InvoiceService,
        orders: OrderService,
        deliver: Deliver,
        mailer: InMemoryMailer,
    ) -> None:
        order_id = await ship()
        await deliver()

        (invoice,) = await invoices.for_order(order_id)
        order = (await orders.get(order_id)).order
        assert invoice.kind is InvoiceKind.INVOICE
        assert invoice.number == "RE-2026-00001"
        assert invoice.source == ORDER_SOURCE
        assert (invoice.total_cents, invoice.tax_cents) == (order.total_cents, order.tax_cents)
        assert invoice.document.startswith(b"%PDF")
        assert invoice.filename == "Rechnung-RE-2026-00001.pdf"

        mail = mails_to(mailer, CUSTOMER)[-1]
        assert mail.subject.endswith("ist unterwegs")
        assert "RE-2026-00001" in mail.text
        (attachment,) = mail.attachments
        assert attachment.filename == invoice.filename
        assert attachment.content == invoice.document
        assert attachment.content_type == "application/pdf"

    async def test_issuing_twice_gives_the_same_invoice(
        self,
        ship: ShipOrder,
        invoices: InvoiceService,
    ) -> None:
        order_id = await ship()
        first, second = await asyncio.gather(
            invoices.invoice_for(order_id), invoices.invoice_for(order_id)
        )
        assert first is not None
        assert second is not None
        assert first.id == second.id
        assert len(await invoices.for_order(order_id)) == 1

    async def test_numbers_run_without_gaps(
        self,
        ship: ShipOrder,
        invoices: InvoiceService,
    ) -> None:
        numbers = []
        for _ in range(3):
            invoice = await invoices.invoice_for(await ship())
            assert invoice is not None
            numbers.append(invoice.number)
        assert numbers == ["RE-2026-00001", "RE-2026-00002", "RE-2026-00003"]

    async def test_an_order_not_shipped_has_no_invoice(
        self,
        invoices: InvoiceService,
        carts: CartService,
        checkout: CheckoutService,
        painted: UUID,
    ) -> None:
        cart = await filled_cart(carts, (painted, 1))
        order = (await place(checkout, carts, cart)).details.order
        assert await invoices.invoice_for(order.id) is None
        assert await invoices.for_order(order.id) == []
        with pytest.raises(OrderNotFoundError):
            await invoices.invoice_for(uuid4())

    async def test_without_a_tax_number_nothing_is_issued(
        self,
        ship: ShipOrder,
        sales_uow: UnitOfWorkFactory,
        clock: FixedClock,
    ) -> None:
        service = InvoiceService(
            uow_factory=sales_uow,
            clock=clock,
            renderer=ReportLabInvoiceRenderer(shop_name="adp-Modelle"),
            issuer=None,
        )
        order_id = await ship()
        assert not service.issues_invoices
        assert await service.invoice_for(order_id) is None
        assert await service.correction_for(refunded(order_id, clock, 100)) is None

    async def test_an_invoice_is_found_only_with_its_order(
        self,
        ship: ShipOrder,
        invoices: InvoiceService,
    ) -> None:
        order_id = await ship()
        invoice = await invoices.invoice_for(order_id)
        assert invoice is not None
        assert (await invoices.get(invoice.id, order_id=order_id)).number == invoice.number
        with pytest.raises(InvoiceNotFoundError):
            await invoices.get(invoice.id, order_id=uuid4())
        with pytest.raises(InvoiceNotFoundError):
            await invoices.get(uuid4())


class TestCorrection:
    async def test_a_refund_after_dispatch_gets_a_correction_in_its_mail(
        self,
        ship: ShipOrder,
        invoices: InvoiceService,
        orders: OrderService,
        deliver: Deliver,
        mailer: InMemoryMailer,
    ) -> None:
        order_id = await ship()
        await deliver()
        total = (await orders.get(order_id)).order.total_cents

        await orders.refund(order_id, amount_cents=total)
        await deliver()

        invoice, correction = sorted(
            await invoices.for_order(order_id), key=lambda i: i.kind is InvoiceKind.CORRECTION
        )
        assert correction.kind is InvoiceKind.CORRECTION
        assert correction.number == "RK-2026-00001"
        assert correction.corrects_id == invoice.id
        assert (correction.total_cents, correction.tax_cents) == (
            -invoice.total_cents,
            -invoice.tax_cents,
        )
        mail = mails_to(mailer, CUSTOMER)[-1]
        assert "RK-2026-00001" in mail.text
        (attachment,) = mail.attachments
        assert attachment.filename == correction.filename
        assert attachment.content.startswith(b"%PDF")

    async def test_a_partial_refund_takes_back_its_vat(
        self,
        ship: ShipOrder,
        invoices: InvoiceService,
        clock: FixedClock,
    ) -> None:
        order_id = await ship()
        await invoices.invoice_for(order_id)
        event = refunded(order_id, clock, 1190)
        correction = await invoices.correction_for(event)
        assert correction is not None
        assert (correction.total_cents, correction.tax_cents) == (-1190, -190)
        # The outbox may deliver the same event again: it finds the same correction.
        again = await invoices.correction_for(event)
        assert again is not None
        assert again.id == correction.id
        # Another refund is another correction, numbered on.
        other = await invoices.correction_for(refunded(order_id, clock, 500))
        assert other is not None
        assert other.number == "RK-2026-00002"

    async def test_a_refund_before_the_invoice_corrects_nothing(
        self,
        invoices: InvoiceService,
        carts: CartService,
        checkout: CheckoutService,
        clock: FixedClock,
        painted: UUID,
    ) -> None:
        cart = await filled_cart(carts, (painted, 1))
        order = (await place(checkout, carts, cart)).details.order
        assert await invoices.correction_for(refunded(order.id, clock, 100)) is None
