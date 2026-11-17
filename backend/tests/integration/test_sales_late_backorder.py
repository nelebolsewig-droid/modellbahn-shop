"""A shelf that empties between checkout and payment (ADR 0029).

The checkout promised "1-3 Werktage" because the pieces were on the shelf; stock is
reserved only when the money comes in. If somebody else took them meanwhile, the order
learns the lead time of what is now made for it, and the customer hears so exactly once.
"""

from uuid import UUID, uuid4

import pytest

from modellbahn.modules.catalog.application.services import CatalogService
from modellbahn.modules.inventory.application.locations import LocationService
from modellbahn.modules.inventory.application.units import UnitService
from modellbahn.modules.media.application.services import MediaService
from modellbahn.modules.sales.application.cart import CartService
from modellbahn.modules.sales.application.checkout import CheckoutService
from modellbahn.modules.sales.application.orders import OrderService
from modellbahn.modules.sales.application.ports import PaymentGateway
from modellbahn.modules.sales.domain.model import BANK_TRANSFER, Order
from modellbahn.platform.mail import InMemoryMailer
from tests.conftest import Deliver
from tests.inventory_support import stock_up
from tests.media_support import InMemoryMediaStorage
from tests.sales_support import FakeSumUp, filled_cart, place, shop_product, variant_id
from tests.support import mails_to

CUSTOMER = "erika@example.de"
OTHER = "max@example.de"
DELAY_SUBJECT = "Kurze Info zu deiner Bestellung"


@pytest.fixture
def payment_gateway() -> PaymentGateway:
    return FakeSumUp()


@pytest.fixture
async def painted(
    catalog: CatalogService,
    media: MediaService,
    media_storage: InMemoryMediaStorage,
    deliver: Deliver,
) -> UUID:
    return variant_id(await shop_product(catalog, media, media_storage, deliver), "H0", "painted")


async def deliver_all(deliver: Deliver) -> None:
    """Run the outbox until it is empty: payment, allocation, lead time and mails follow
    one another."""
    for _ in range(10):
        if not await deliver():
            return
    pytest.fail("the outbox does not run dry")


async def by_transfer(
    carts: CartService,
    checkout: CheckoutService,
    variant: UUID,
    quantity: int = 1,
    *,
    email: str = CUSTOMER,
) -> Order:
    cart = await filled_cart(carts, (variant, quantity))
    order = (await place(checkout, carts, cart, email=email)).details.order
    result = await checkout.pay(
        public_token=order.public_token, method=BANK_TRANSFER, idempotency_key=uuid4()
    )
    return result.details.order


def delay_mails(mailer: InMemoryMailer, email: str = CUSTOMER) -> list[str]:
    return [m.text for m in mails_to(mailer, email) if m.subject.startswith(DELAY_SUBJECT)]


class TestShelfEmptiedBeforePayment:
    async def test_the_order_learns_the_lead_time_and_the_customer_hears_once(
        self,
        carts: CartService,
        checkout: CheckoutService,
        orders: OrderService,
        deliver: Deliver,
        mailer: InMemoryMailer,
        painted: UUID,
        locations: LocationService,
        units: UnitService,
    ) -> None:
        await stock_up(locations, units, painted, 2)
        # Erika sees both on the shelf and chooses a transfer: the checkout promises days.
        waiting = await by_transfer(carts, checkout, painted, 2)
        assert waiting.lead_time_weeks is None
        # Max takes one of them and pays first.
        other = await by_transfer(carts, checkout, painted, email=OTHER)
        await orders.confirm_bank_transfer(other.id)
        await deliver_all(deliver)
        # Erika's money comes in: one is on the shelf, one is made for her.
        await orders.confirm_bank_transfer(waiting.id)
        await deliver_all(deliver)

        delayed = (await orders.get(waiting.id)).order
        assert delayed.lead_time_weeks == (2, 4)
        [notice] = delay_mails(mailer)
        assert waiting.number in notice
        assert "Stellwerk Altenau" in notice
        assert "voraussichtlich in 2\u20134 Wochen" in notice
        # Max got his from the shelf and hears nothing of it.
        assert delay_mails(mailer, OTHER) == []
        assert (await orders.get(other.id)).order.lead_time_weeks is None

    async def test_several_missing_pieces_still_make_one_notice(
        self,
        carts: CartService,
        checkout: CheckoutService,
        orders: OrderService,
        deliver: Deliver,
        mailer: InMemoryMailer,
        painted: UUID,
        locations: LocationService,
        units: UnitService,
    ) -> None:
        await stock_up(locations, units, painted, 3)
        waiting = await by_transfer(carts, checkout, painted, 3)
        other = await by_transfer(carts, checkout, painted, 3, email=OTHER)
        await orders.confirm_bank_transfer(other.id)
        await deliver_all(deliver)
        await orders.confirm_bank_transfer(waiting.id)
        await deliver_all(deliver)

        assert (await orders.get(waiting.id)).order.lead_time_weeks == (2, 4)
        assert len(delay_mails(mailer)) == 1

    async def test_a_lead_time_promised_at_the_checkout_needs_no_notice(
        self,
        carts: CartService,
        checkout: CheckoutService,
        orders: OrderService,
        deliver: Deliver,
        mailer: InMemoryMailer,
        painted: UUID,
        locations: LocationService,
        units: UnitService,
    ) -> None:
        await stock_up(locations, units, painted)
        # Two while one is on the shelf: the checkout already said 2-4 weeks.
        promised = await by_transfer(carts, checkout, painted, 2)
        assert promised.lead_time_weeks == (2, 4)
        await orders.confirm_bank_transfer(promised.id)
        await deliver_all(deliver)

        assert (await orders.get(promised.id)).order.lead_time_weeks == (2, 4)
        assert delay_mails(mailer) == []

    async def test_everything_on_the_shelf_needs_no_notice(
        self,
        carts: CartService,
        checkout: CheckoutService,
        orders: OrderService,
        deliver: Deliver,
        mailer: InMemoryMailer,
        painted: UUID,
        locations: LocationService,
        units: UnitService,
    ) -> None:
        await stock_up(locations, units, painted, 2)
        order = await by_transfer(carts, checkout, painted, 2)
        await orders.confirm_bank_transfer(order.id)
        await deliver_all(deliver)

        assert (await orders.get(order.id)).order.lead_time_weeks is None
        assert delay_mails(mailer) == []
