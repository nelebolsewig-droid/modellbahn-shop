"""Use cases of the checkout: turn the cart into an order, and pay for it.

Both requests carry an ``Idempotency-Key``. It is stored with the order or the payment,
in the same transaction, together with a fingerprint of the request: repeating the
request returns what the first one did, a different request with the same key is
refused. A double click or a retry after a lost answer thus never orders or charges twice.
"""

from dataclasses import asdict, dataclass
from uuid import UUID

from modellbahn.modules.sales.application.cart import price_cart
from modellbahn.modules.sales.application.common import (
    OrderDetails,
    UnitOfWorkFactory,
    fingerprint,
    order_details,
)
from modellbahn.modules.sales.application.ports import PaymentGateway, SalesUnitOfWork
from modellbahn.modules.sales.domain.errors import (
    AddressNotFoundError,
    CartItemsUnavailableError,
    EmptyCartError,
    IdempotencyKeyReusedError,
    InvalidFieldError,
    OrderNotFoundError,
    PriceChangedError,
)
from modellbahn.modules.sales.domain.model import (
    ADDRESS_BOOK_MAX_SIZE,
    Cart,
    CustomerAddress,
    Order,
    PostalAddress,
    PricedItem,
    Totals,
    normalize_email,
    order_number,
)
from modellbahn.platform.clock import Clock
from modellbahn.platform.security import generate_token
from modellbahn.platform.uow import UniqueViolationError


@dataclass(frozen=True, slots=True)
class AddressInput:
    recipient: str
    street: str
    postal_code: str
    city: str
    country_code: str

    def to_address(self) -> PostalAddress:
        return PostalAddress.create(
            recipient=self.recipient,
            street=self.street,
            postal_code=self.postal_code,
            city=self.city,
            country_code=self.country_code,
        )


@dataclass(frozen=True, slots=True)
class CheckoutRequest:
    """What the customer confirmed on the review page.

    Guests give an e-mail address and an address; customers may pick an address from
    their book instead (``address_id``) or keep a new one there (``save_address``).
    ``expected_total_cents`` is the total the customer saw: if prices changed since,
    nothing is ordered.
    """

    expected_total_cents: int
    email: str | None = None
    address: AddressInput | None = None
    address_id: UUID | None = None
    save_address: bool = False


@dataclass(frozen=True, slots=True)
class Buyer:
    """The logged-in customer placing the order (absent for guests)."""

    account_id: UUID
    email: str


@dataclass(frozen=True, slots=True)
class CheckoutResult:
    details: OrderDetails
    replayed: bool
    """True if the key was seen before and this is the first request's order."""


class CheckoutService:
    def __init__(
        self, *, uow_factory: UnitOfWorkFactory, clock: Clock, gateway: PaymentGateway
    ) -> None:
        self._uow = uow_factory
        self._clock = clock
        self._gateway = gateway

    async def place_order(
        self,
        *,
        cart_id: UUID | None,
        request: CheckoutRequest,
        buyer: Buyer | None,
        idempotency_key: UUID,
    ) -> CheckoutResult:
        """Order what is in the cart, at today's prices; the cart is empty afterwards."""
        request_fingerprint = fingerprint(
            {
                "cart": cart_id,
                "buyer": buyer.account_id if buyer else None,
                "request": asdict(request),
            }
        )
        try:
            async with self._uow() as uow:
                # Lock the cart before looking for the key: a parallel request with the
                # same key then waits here, and finds the order once the first one is done
                # (instead of a cart it has just emptied).
                cart = await uow.carts.get(cart_id, for_update=True) if cart_id else None
                replay = await self._replay_checkout(uow, idempotency_key, request_fingerprint)
                if replay is not None:
                    return replay
                order = await self._place(
                    uow,
                    cart,
                    request,
                    buyer,
                    idempotency_key=idempotency_key,
                    request_fingerprint=request_fingerprint,
                )
                await uow.commit()
                return CheckoutResult(details=await order_details(uow, order), replayed=False)
        except UniqueViolationError as exc:
            if exc.constraint != "uq_orders_checkout_key":
                raise
        # A parallel request with the same key won the race; answer with its order.
        async with self._uow() as uow:
            replay = await self._replay_checkout(uow, idempotency_key, request_fingerprint)
            if replay is None:  # pragma: no cover - the winner committed before we failed
                raise RuntimeError("checkout key conflict without an order")
            return replay

    async def pay(self, *, public_token: str, method: str, idempotency_key: UUID) -> CheckoutResult:
        """Charge the order's total; a captured payment makes it binding."""
        request_fingerprint = fingerprint({"order": public_token, "method": method})
        try:
            async with self._uow() as uow:
                order = await uow.orders.get_by_token(public_token, for_update=True)
                if order is None:
                    raise OrderNotFoundError
                replay = await self._replay_payment(
                    uow, order, idempotency_key, request_fingerprint
                )
                if replay is not None:
                    return replay
                # The row lock keeps a second payment attempt waiting until this one is
                # recorded; record_payment then refuses an order that is no longer open.
                result = await self._gateway.charge(
                    order_number=order.number, amount_cents=order.total_cents, method=method
                )
                events = order.record_payment(
                    result,
                    idempotency_key=idempotency_key,
                    request_fingerprint=request_fingerprint,
                    now=self._clock.now(),
                )
                uow.publish(*events)
                await uow.commit()
                return CheckoutResult(details=await order_details(uow, order), replayed=False)
        except UniqueViolationError as exc:
            if exc.constraint != "uq_payments_idempotency_key":
                raise
        async with self._uow() as uow:
            order = await uow.orders.get_by_token(public_token)
            if order is None:  # pragma: no cover - orders are never deleted
                raise OrderNotFoundError from None
            replay = await self._replay_payment(uow, order, idempotency_key, request_fingerprint)
            if replay is None:
                # The key was used for the payment of another order.
                raise IdempotencyKeyReusedError from None
            return replay

    async def _place(
        self,
        uow: SalesUnitOfWork,
        cart: Cart | None,
        request: CheckoutRequest,
        buyer: Buyer | None,
        *,
        idempotency_key: UUID,
        request_fingerprint: str,
    ) -> Order:
        now = self._clock.now()
        if cart is None or cart.is_expired(now) or not cart.lines:
            raise EmptyCartError
        priced = await price_cart(uow, cart)
        unavailable = [item.variant.variant_id for item in priced.items if not item.available]
        if unavailable:
            raise CartItemsUnavailableError(unavailable)
        if not priced.items:
            raise EmptyCartError

        address, book = await self._address(uow, request, buyer)
        email = buyer.email if buyer is not None else _guest_email(request.email)
        items = [
            PricedItem(
                variant_id=item.variant.variant_id,
                product_slug=item.variant.product_slug,
                sku=item.variant.sku,
                title=item.variant.title,
                scale_code=item.variant.scale_code,
                finish_code=item.variant.finish_code,
                unit_price_cents=item.variant.price_cents,
                quantity=item.quantity,
                image_asset_id=item.variant.image_asset_id,
            )
            for item in priced.items
        ]
        totals = Totals.of(sum(i.unit_price_cents * i.quantity for i in items), address.zone)
        if totals.total_cents != request.expected_total_cents:
            raise PriceChangedError(
                expected_cents=request.expected_total_cents, actual_cents=totals.total_cents
            )

        account_id = buyer.account_id if buyer else await uow.accounts.verified_customer(email)
        order, placed = Order.place(
            number=order_number(now.year, await uow.orders.next_serial()),
            public_token=generate_token(),
            items=items,
            email=email,
            address=address,
            customer_account_id=account_id,
            checkout_key=idempotency_key,
            checkout_fingerprint=request_fingerprint,
            now=now,
        )
        uow.orders.add(order)
        uow.publish(placed)
        # A full address book is no reason to refuse the order; the address is just not kept.
        if (
            buyer is not None
            and request.save_address
            and request.address_id is None
            and len(book) < ADDRESS_BOOK_MAX_SIZE
        ):
            uow.addresses.add(
                CustomerAddress.create(
                    account_id=buyer.account_id, label="", address=address, existing=book, now=now
                )
            )
        cart.clear(now)
        return order

    async def _address(
        self, uow: SalesUnitOfWork, request: CheckoutRequest, buyer: Buyer | None
    ) -> tuple[PostalAddress, list[CustomerAddress]]:
        book = await uow.addresses.book(buyer.account_id) if buyer is not None else []
        if request.address_id is not None:
            entry = next((a for a in book if a.id == request.address_id), None)
            if entry is None:
                raise AddressNotFoundError
            return entry.address, book
        if request.address is None:
            raise InvalidFieldError("address", "required", "an address or address_id is needed")
        return request.address.to_address(), book

    async def _replay_checkout(
        self, uow: SalesUnitOfWork, key: UUID, request_fingerprint: str
    ) -> CheckoutResult | None:
        order = await uow.orders.get_by_checkout_key(key)
        if order is None:
            return None
        if order.checkout_fingerprint != request_fingerprint:
            raise IdempotencyKeyReusedError
        return CheckoutResult(details=await order_details(uow, order), replayed=True)

    async def _replay_payment(
        self, uow: SalesUnitOfWork, order: Order, key: UUID, request_fingerprint: str
    ) -> CheckoutResult | None:
        payment = order.payment_with_key(key)
        if payment is None:
            return None
        if payment.request_fingerprint != request_fingerprint:
            raise IdempotencyKeyReusedError
        return CheckoutResult(details=await order_details(uow, order), replayed=True)


def _guest_email(email: str | None) -> str:
    if email is None or not email.strip():
        raise InvalidFieldError("email", "required", "guests need an e-mail address")
    return normalize_email(email)
