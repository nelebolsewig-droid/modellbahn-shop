"""The withdrawal function against the database (§ 356a BGB, ADR 0020).

A declaration is stored with the time it came in; the worker confirms it to the consumer
and tells the shop. Unknown numbers are taken all the same.
"""

from datetime import timedelta
from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from modellbahn.modules.catalog.application.services import CatalogService
from modellbahn.modules.media.application.services import MediaService
from modellbahn.modules.sales.application.cart import CartService
from modellbahn.modules.sales.application.checkout import CheckoutService
from modellbahn.modules.sales.application.withdrawals import WithdrawalService
from modellbahn.modules.sales.domain.errors import InvalidFieldError
from modellbahn.modules.sales.domain.model import Order
from modellbahn.platform.clock import FixedClock
from modellbahn.platform.mail import InMemoryMailer
from tests.conftest import PUBLIC_BASE_URL, SHOP_EMAIL, Deliver
from tests.integration.test_sales_service import event_types
from tests.media_support import InMemoryMediaStorage
from tests.sales_support import filled_cart, place, shop_product, variant_id
from tests.support import mails_to


@pytest.fixture
async def order(
    catalog: CatalogService,
    media: MediaService,
    media_storage: InMemoryMediaStorage,
    deliver: Deliver,
    carts: CartService,
    checkout: CheckoutService,
) -> Order:
    product = await shop_product(catalog, media, media_storage, deliver)
    cart = await filled_cart(carts, (variant_id(product, "H0", "painted"), 1))
    placed = (await place(checkout, carts, cart)).details.order
    await deliver()  # the order's own mails go out first
    return placed


class TestWithdrawalFunction:
    async def test_a_declaration_is_confirmed_and_reported(
        self,
        withdrawals: WithdrawalService,
        order: Order,
        deliver: Deliver,
        mailer: InMemoryMailer,
        engine: AsyncEngine,
        clock: FixedClock,
    ) -> None:
        received = await withdrawals.declare(
            name="Erika Mustermann",
            order_number=order.number.lower(),
            email="ERIKA@example.de",
            scope="",
        )
        assert received.order_id == order.id
        assert received.received_at == clock.now()
        assert "sales.withdrawal.received" in await event_types(engine)

        await deliver()
        (receipt,) = mails_to(mailer, "ERIKA@example.de")
        assert receipt.subject == f"Eingangsbestätigung: dein Widerruf zu Bestellung {order.number}"
        assert "Widerrufen: die ganze Bestellung." in receipt.text
        assert "Die Kosten der Rücksendung trägst du." in receipt.text
        (notice,) = mails_to(mailer, SHOP_EMAIL)
        assert notice.subject == f"Widerruf eingegangen: {order.number}"
        assert f"{PUBLIC_BASE_URL}/admin/bestellungen/{order.id}" in notice.text

    async def test_an_unknown_number_is_taken_all_the_same(
        self,
        withdrawals: WithdrawalService,
        order: Order,
        deliver: Deliver,
        mailer: InMemoryMailer,
    ) -> None:
        # Right number, other address: no order is named, and the answer is the same.
        other = await withdrawals.declare(
            name="Max Muster", order_number=order.number, email="max@example.de", scope=""
        )
        unknown = await withdrawals.declare(
            name="Max Muster",
            order_number="MB-1999-00001",
            email="max@example.de",
            scope="den Prellbock",
        )
        assert (other.order_id, unknown.order_id) == (None, None)
        await deliver()
        assert len(mails_to(mailer, "max@example.de")) == 2
        notices = mails_to(mailer, SHOP_EMAIL)
        assert all("passt keine Bestellung" in mail.text for mail in notices)
        assert len(notices) == 2

    async def test_staff_see_the_latest_first_and_per_order(
        self, withdrawals: WithdrawalService, order: Order, clock: FixedClock
    ) -> None:
        first = await withdrawals.declare(
            name="Erika Mustermann", order_number=order.number, email=order.email, scope=""
        )
        clock.advance(timedelta(minutes=5))
        later = await withdrawals.declare(
            name="Max Muster", order_number="MB-1999-00001", email="max@example.de", scope=""
        )
        recent = await withdrawals.recent(limit=10)
        assert [w.id for w in recent] == [later.id, first.id]
        for_order = await withdrawals.recent(limit=10, order_id=order.id)
        assert [w.id for w in for_order] == [first.id]
        assert await withdrawals.recent(limit=10, order_id=UUID(int=0)) == []

    async def test_what_cannot_be_confirmed_is_refused(
        self, withdrawals: WithdrawalService
    ) -> None:
        with pytest.raises(InvalidFieldError):
            await withdrawals.declare(
                name="Erika", order_number="MB-2026-00042", email="keine-adresse", scope=""
            )
        # An absurdly long number is no order of ours, and still not a crash.
        with pytest.raises(InvalidFieldError):
            await withdrawals.declare(
                name="Erika", order_number="M" * 41, email="erika@example.de", scope=""
            )
        assert await withdrawals.recent(limit=10) == []
