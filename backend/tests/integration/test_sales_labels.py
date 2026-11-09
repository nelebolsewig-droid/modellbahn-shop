"""Shipping labels against the database (ADR 0023).

The packer books the label of a picked order with the test carrier; dispatching then takes
its number into the customer's e-mail. A wrong label is cancelled at the carrier; a
cancelled order takes its label along.
"""

from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

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
from modellbahn.modules.sales.application.labels import ShippingLabelService
from modellbahn.modules.sales.application.orders import OrderService
from modellbahn.modules.sales.application.ports import BookedLabel, LabelRequest
from modellbahn.modules.sales.domain.errors import (
    CarrierRejectedError,
    CarrierUnavailableError,
    InvalidFieldError,
    InvalidOrderStateError,
    LabelExistsError,
    LabelNotFoundError,
    OrderNotFoundError,
)
from modellbahn.modules.sales.domain.events import OrderCancelled
from modellbahn.modules.sales.domain.labels import LabelStatus, ShippingProduct
from modellbahn.modules.sales.domain.model import OrderStatus
from modellbahn.modules.sales.infrastructure.carriers import TEST_SHIPPER, NoCarrier, TestCarrier
from modellbahn.platform.clock import FixedClock
from modellbahn.platform.mail import InMemoryMailer
from tests.conftest import Deliver
from tests.inventory_support import pick_everything, staff_member, stock_up
from tests.media_support import InMemoryMediaStorage
from tests.sales_support import filled_cart, place, shop_product, variant_id
from tests.support import mails_to

CUSTOMER = "erika@example.de"


class RefusingCarrier(TestCarrier):
    """Books like the test carrier, but refuses or fails on cancelling."""

    def __init__(self, error: Exception) -> None:
        super().__init__()
        self.error = error
        self.requests: list[LabelRequest] = []

    async def book(self, request: LabelRequest) -> BookedLabel:
        self.requests.append(request)
        return await super().book(request)

    async def cancel(self, shipment_number: str) -> None:
        raise self.error


@pytest.fixture
def carrier() -> TestCarrier:
    return TestCarrier()


@pytest.fixture
def labels(
    sales_uow: UnitOfWorkFactory, clock: FixedClock, carrier: TestCarrier
) -> ShippingLabelService:
    return ShippingLabelService(
        uow_factory=sales_uow,
        clock=clock,
        carrier=carrier,
        shipper=TEST_SHIPPER,
        default_weight_g=1000,
    )


@pytest.fixture
async def painted(
    catalog: CatalogService,
    media: MediaService,
    media_storage: InMemoryMediaStorage,
    deliver: Deliver,
) -> UUID:
    return variant_id(await shop_product(catalog, media, media_storage, deliver), "H0", "painted")


async def paid_order(carts: CartService, checkout: CheckoutService, painted: UUID) -> UUID:
    cart = await filled_cart(carts, (painted, 1))
    order = (await place(checkout, carts, cart)).details.order
    await checkout.pay(public_token=order.public_token, method="succeeds", idempotency_key=uuid4())
    return order.id


async def cancel_order(orders: OrderService, order_id: UUID, clock: FixedClock) -> OrderCancelled:
    """Cancel the order; the event the worker hands to the label service then."""
    cancelled = (await orders.cancel(order_id, note="")).order
    return OrderCancelled(
        aggregate_id=order_id,
        occurred_at=clock.now(),
        number=cancelled.number,
        total_cents=cancelled.total_cents,
        refunded=True,
    )


class TestBooking:
    async def test_a_paid_order_gets_one_label(
        self,
        labels: ShippingLabelService,
        carts: CartService,
        checkout: CheckoutService,
        painted: UUID,
    ) -> None:
        order_id = await paid_order(carts, checkout, painted)
        label = await labels.book(order_id, weight_g=850)
        assert label.status is LabelStatus.ACTIVE
        assert label.product is ShippingProduct.PARCEL
        assert label.weight_g == 850
        assert label.document.startswith(b"%PDF")
        assert len(label.shipment_number) == 12
        assert (await labels.active(order_id)).shipment_number == label.shipment_number
        with pytest.raises(LabelExistsError):
            await labels.book(order_id)

    async def test_the_default_weight_and_the_request(
        self,
        sales_uow: UnitOfWorkFactory,
        clock: FixedClock,
        carts: CartService,
        checkout: CheckoutService,
        painted: UUID,
    ) -> None:
        carrier = RefusingCarrier(CarrierUnavailableError())
        service = ShippingLabelService(
            uow_factory=sales_uow,
            clock=clock,
            carrier=carrier,
            shipper=TEST_SHIPPER,
            default_weight_g=1200,
        )
        order_id = await paid_order(carts, checkout, painted)
        label = await service.book(order_id)
        assert label.weight_g == 1200
        request = carrier.requests[0]
        assert request.reference.startswith("MB-")
        assert request.shipper == TEST_SHIPPER
        assert (request.consignee.country, request.weight_g) == ("DEU", 1200)

    async def test_only_paid_orders_get_labels(
        self,
        labels: ShippingLabelService,
        carts: CartService,
        checkout: CheckoutService,
        painted: UUID,
    ) -> None:
        cart = await filled_cart(carts, (painted, 1))
        order = (await place(checkout, carts, cart)).details.order
        with pytest.raises(InvalidOrderStateError):
            await labels.book(order.id)
        with pytest.raises(OrderNotFoundError):
            await labels.book(uuid4())

    async def test_a_weight_dhl_does_not_carry(
        self,
        labels: ShippingLabelService,
        carts: CartService,
        checkout: CheckoutService,
        painted: UUID,
    ) -> None:
        order_id = await paid_order(carts, checkout, painted)
        with pytest.raises(InvalidFieldError):
            await labels.book(order_id, weight_g=40_000)
        with pytest.raises(LabelNotFoundError):
            await labels.active(order_id)

    async def test_without_a_carrier_or_sender_nothing_is_booked(
        self,
        sales_uow: UnitOfWorkFactory,
        clock: FixedClock,
        carts: CartService,
        checkout: CheckoutService,
        painted: UUID,
    ) -> None:
        order_id = await paid_order(carts, checkout, painted)
        for carrier, shipper in ((NoCarrier(), TEST_SHIPPER), (TestCarrier(), None)):
            service = ShippingLabelService(
                uow_factory=sales_uow,
                clock=clock,
                carrier=carrier,
                shipper=shipper,
                default_weight_g=1000,
            )
            assert not service.books_labels
            with pytest.raises(CarrierUnavailableError):
                await service.book(order_id)


class TestCancelling:
    async def test_a_wrong_label_is_cancelled_and_booked_anew(
        self,
        labels: ShippingLabelService,
        carrier: TestCarrier,
        carts: CartService,
        checkout: CheckoutService,
        painted: UUID,
    ) -> None:
        order_id = await paid_order(carts, checkout, painted)
        wrong = await labels.book(order_id, weight_g=500)
        await labels.cancel(order_id)
        assert carrier.cancelled == [wrong.shipment_number]
        with pytest.raises(LabelNotFoundError):
            await labels.active(order_id)
        with pytest.raises(LabelNotFoundError):
            await labels.cancel(order_id)
        right = await labels.book(order_id, weight_g=900)
        assert (await labels.active(order_id)).shipment_number == right.shipment_number

    async def test_a_refusal_keeps_the_label(
        self,
        sales_uow: UnitOfWorkFactory,
        clock: FixedClock,
        carts: CartService,
        checkout: CheckoutService,
        painted: UUID,
    ) -> None:
        service = ShippingLabelService(
            uow_factory=sales_uow,
            clock=clock,
            carrier=RefusingCarrier(CarrierRejectedError("Sendung bereits manifestiert")),
            shipper=TEST_SHIPPER,
            default_weight_g=1000,
        )
        order_id = await paid_order(carts, checkout, painted)
        label = await service.book(order_id)
        with pytest.raises(CarrierRejectedError):
            await service.cancel(order_id)
        assert (await service.active(order_id)).shipment_number == label.shipment_number

    async def test_a_cancelled_order_takes_its_label_along(
        self,
        labels: ShippingLabelService,
        carrier: TestCarrier,
        orders: OrderService,
        carts: CartService,
        checkout: CheckoutService,
        clock: FixedClock,
        painted: UUID,
    ) -> None:
        order_id = await paid_order(carts, checkout, painted)
        label = await labels.book(order_id)
        event = await cancel_order(orders, order_id, clock)
        await labels.cancel_with_order(event)
        assert carrier.cancelled == [label.shipment_number]
        with pytest.raises(LabelNotFoundError):
            await labels.active(order_id)
        # Delivered twice (the outbox retries): nothing left to do.
        await labels.cancel_with_order(event)
        assert carrier.cancelled == [label.shipment_number]

    async def test_a_label_the_carrier_no_longer_knows_goes_too(
        self,
        sales_uow: UnitOfWorkFactory,
        clock: FixedClock,
        orders: OrderService,
        carts: CartService,
        checkout: CheckoutService,
        painted: UUID,
    ) -> None:
        service = ShippingLabelService(
            uow_factory=sales_uow,
            clock=clock,
            carrier=RefusingCarrier(CarrierRejectedError("unbekannte Sendung")),
            shipper=TEST_SHIPPER,
            default_weight_g=1000,
        )
        order_id = await paid_order(carts, checkout, painted)
        await service.book(order_id)
        event = await cancel_order(orders, order_id, clock)
        await service.cancel_with_order(event)
        with pytest.raises(LabelNotFoundError):
            await service.active(order_id)

    async def test_an_unreachable_carrier_is_tried_again(
        self,
        sales_uow: UnitOfWorkFactory,
        clock: FixedClock,
        orders: OrderService,
        carts: CartService,
        checkout: CheckoutService,
        painted: UUID,
    ) -> None:
        service = ShippingLabelService(
            uow_factory=sales_uow,
            clock=clock,
            carrier=RefusingCarrier(CarrierUnavailableError()),
            shipper=TEST_SHIPPER,
            default_weight_g=1000,
        )
        order_id = await paid_order(carts, checkout, painted)
        label = await service.book(order_id)
        event = await cancel_order(orders, order_id, clock)
        # The outbox sees the failure and delivers the event again later.
        with pytest.raises(CarrierUnavailableError):
            await service.cancel_with_order(event)
        assert (await service.active(order_id)).shipment_number == label.shipment_number

    async def test_with_the_carrier_switched_off_the_label_goes_here(
        self,
        labels: ShippingLabelService,
        sales_uow: UnitOfWorkFactory,
        orders: OrderService,
        carts: CartService,
        checkout: CheckoutService,
        clock: FixedClock,
        painted: UUID,
    ) -> None:
        order_id = await paid_order(carts, checkout, painted)
        await labels.book(order_id)
        event = await cancel_order(orders, order_id, clock)
        switched_off = ShippingLabelService(
            uow_factory=sales_uow,
            clock=clock,
            carrier=NoCarrier(),
            shipper=TEST_SHIPPER,
            default_weight_g=1000,
        )
        await switched_off.cancel_with_order(event)
        with pytest.raises(LabelNotFoundError):
            await labels.active(order_id)


class TestDispatch:
    async def test_the_label_number_reaches_the_customer(
        self,
        labels: ShippingLabelService,
        orders: OrderService,
        carts: CartService,
        checkout: CheckoutService,
        deliver: Deliver,
        mailer: InMemoryMailer,
        identity: IdentityService,
        locations: LocationService,
        units: UnitService,
        scans: ScanService,
        allocation: AllocationService,
        engine: AsyncEngine,
        painted: UUID,
    ) -> None:
        await stock_up(locations, units, painted)
        order_id = await paid_order(carts, checkout, painted)
        await deliver()
        await pick_everything(scans, allocation, order_id, await staff_member(identity))
        label = await labels.book(order_id, weight_g=850)

        shipped = (await orders.ship(order_id, carrier="", tracking_number="")).order
        assert shipped.status is OrderStatus.SHIPPED
        assert (shipped.carrier, shipped.tracking_number) == ("DHL", label.shipment_number)
        # The parcel is on its way with this label: it stays in force.
        with pytest.raises(InvalidOrderStateError):
            await labels.cancel(order_id)
        assert (await labels.active(order_id)).shipment_number == label.shipment_number

        await deliver()
        mail = mails_to(mailer, CUSTOMER)[-1]
        assert mail.subject.endswith("ist unterwegs")
        assert label.shipment_number in mail.text
        assert f"piececode={label.shipment_number}" in mail.text

    async def test_a_typed_number_wins_over_the_label(
        self,
        labels: ShippingLabelService,
        orders: OrderService,
        carts: CartService,
        checkout: CheckoutService,
        deliver: Deliver,
        identity: IdentityService,
        locations: LocationService,
        units: UnitService,
        scans: ScanService,
        allocation: AllocationService,
        painted: UUID,
    ) -> None:
        await stock_up(locations, units, painted)
        order_id = await paid_order(carts, checkout, painted)
        await deliver()
        await pick_everything(scans, allocation, order_id, await staff_member(identity))
        await labels.book(order_id)
        shipped = (await orders.ship(order_id, carrier="Hermes", tracking_number="H123")).order
        assert (shipped.carrier, shipped.tracking_number) == ("Hermes", "H123")
