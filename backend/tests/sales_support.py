"""Helpers for sales tests: products in the shop, a filled cart, a placed order."""

from collections.abc import Sequence
from itertools import count
from typing import Final, Literal
from uuid import UUID, uuid4

from modellbahn.modules.catalog.application.services import CatalogService, ProductDetails
from modellbahn.modules.catalog.domain.model import Dimensions
from modellbahn.modules.media.application.services import MediaService
from modellbahn.modules.sales.application.cart import CartService
from modellbahn.modules.sales.application.checkout import (
    AddressInput,
    Buyer,
    CheckoutRequest,
    CheckoutResult,
    CheckoutService,
)
from modellbahn.modules.sales.application.ports import PaymentRequest
from modellbahn.modules.sales.domain.errors import PaymentUnavailableError
from modellbahn.modules.sales.domain.model import PaymentOutcome, PaymentProgress, PaymentStart
from tests.conftest import Deliver
from tests.media_support import InMemoryMediaStorage, photo, ready_image

type VariantSpec = tuple[str, str, int]
"""Gauge, finish and price in cents."""

DEFAULT_VARIANTS: Sequence[VariantSpec] = (("H0", "painted", 4990), ("H0", "unpainted", 2990))

ADDRESS = AddressInput(
    recipient="Erika Mustermann",
    street="Bahnhofstraße 12",
    postal_code="38707",
    city="Altenau",
    country_code="DE",
)

_colours = count(1)


async def shop_product(
    catalog: CatalogService,
    media: MediaService,
    media_storage: InMemoryMediaStorage,
    deliver: Deliver,
    *,
    name: str = "Stellwerk Altenau",
    variants: Sequence[VariantSpec] = DEFAULT_VARIANTS,
    made_to_order: bool = True,
) -> ProductDetails:
    """A published product with the given variants and a ready main image.

    Its variants are made to order unless told otherwise, so they can be bought
    without stock.
    """
    details = await catalog.create_product(name=name)
    category = await catalog.create_category(name=f"Kategorie {uuid4().hex[:6]}")
    product_id = details.product.id
    await catalog.change_product(product_id, expected_version=None, primary_category_id=category.id)
    for scale_code in dict.fromkeys(spec[0] for spec in variants):
        details = await catalog.add_scale(
            product_id, expected_version=None, scale_code=scale_code, dimensions=Dimensions()
        )
        scale = next(s for s in details.product.scales if s.scale_code == scale_code)
        for _, finish, price in (spec for spec in variants if spec[0] == scale_code):
            details = await catalog.add_variant(
                scale.id,
                expected_version=None,
                finish_code=finish,
                price_cents=price,
                allow_backorder=made_to_order,
            )
    shade = next(_colours) % 250
    image = await ready_image(
        media, media_storage, deliver, photo(480, 400, colour=(shade, 200 - shade % 200, 90))
    )
    await catalog.attach_image(product_id, asset_id=image.id)
    return await catalog.publish(product_id, expected_version=None)


def variant_id(details: ProductDetails, scale_code: str, finish_code: str) -> UUID:
    scale = next(s for s in details.product.scales if s.scale_code == scale_code)
    return next(v.id for v in scale.variants if v.finish_code == finish_code)


async def filled_cart(carts: CartService, *lines: tuple[UUID, int]) -> UUID:
    """A new cart with the given variants and quantities; its id."""
    cart: UUID | None = None
    for variant, quantity in lines:
        view = await carts.set_quantity(cart, variant, quantity)
        cart = view.cart_id
    assert cart is not None
    return cart


async def place(
    checkout: CheckoutService,
    carts: CartService,
    cart: UUID,
    *,
    email: str | None = "erika@example.de",
    buyer: Buyer | None = None,
    address: AddressInput | None = ADDRESS,
    key: UUID | None = None,
) -> CheckoutResult:
    """Check out the cart with the total it shows now."""
    view = await carts.view(cart)
    request = CheckoutRequest(
        expected_total_cents=view.totals.total_cents,
        email=None if buyer else email,
        address=address,
    )
    return await checkout.place_order(
        cart_id=cart, request=request, buyer=buyer, idempotency_key=key or uuid4()
    )


type CheckoutState = Literal["PENDING", "PAID", "EXPIRED"]

SUMUP: Final = "sumup"


class FakeSumUp:
    """SumUp as the shop sees it: checkouts with a page, their state, refunds."""

    provider = SUMUP
    takes_payments = True

    def __init__(self) -> None:
        self.checkouts: dict[str, CheckoutState] = {}
        self.requests: list[PaymentRequest] = []
        self.closed: list[str] = []
        self.refunds: list[tuple[str, int]] = []
        self.reachable = True
        self.refuses_to_close = False

    # What the customer does on the page.

    def pay(self, reference: str) -> None:
        self.checkouts[reference] = "PAID"

    def expire(self, reference: str) -> None:
        self.checkouts[reference] = "EXPIRED"

    # The API the shop calls.

    async def begin(self, request: PaymentRequest) -> PaymentStart:
        self._answer()
        reference = f"chk_{len(self.checkouts) + 1}"
        self.checkouts[reference] = "PENDING"
        self.requests.append(request)
        return PaymentStart(
            provider=SUMUP,
            provider_ref=reference,
            checkout_url=f"https://pay.sumup.test/{reference}",
        )

    async def outcome(self, provider_ref: str) -> PaymentOutcome:
        self._answer()
        match self.checkouts[provider_ref]:
            case "PAID":
                return PaymentOutcome(
                    progress=PaymentProgress.CAPTURED, transaction_ref=f"txn_{provider_ref}"
                )
            case "EXPIRED":
                return PaymentOutcome(progress=PaymentProgress.FAILED, failure_code="expired")
            case "PENDING":
                return PaymentOutcome(progress=PaymentProgress.PENDING)

    async def abandon(self, provider_ref: str) -> None:
        self._answer()
        if self.refuses_to_close or self.checkouts[provider_ref] != "PENDING":
            raise PaymentUnavailableError
        self.checkouts[provider_ref] = "EXPIRED"
        self.closed.append(provider_ref)

    async def refund(self, *, refund_ref: str, amount_cents: int) -> None:
        self._answer()
        self.refunds.append((refund_ref, amount_cents))

    async def aclose(self) -> None:
        return

    def _answer(self) -> None:
        if not self.reachable:
            raise PaymentUnavailableError
