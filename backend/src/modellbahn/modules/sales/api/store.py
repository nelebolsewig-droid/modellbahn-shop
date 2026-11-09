"""Shop API of the sales module: cart, checkout, status page and payment (``/api/v1/store``)."""

from uuid import UUID

from fastapi import APIRouter, Depends, Response, status

from modellbahn.modules.sales.api.deps import (
    PRIVATE_CACHE_CONTROL,
    CartId,
    CartServiceDep,
    CheckoutServiceDep,
    IdempotencyKey,
    OptionalCustomer,
    OrderServiceDep,
    PaymentServiceDep,
    SettingsDep,
    WithdrawalServiceDep,
    limit_checkouts,
    set_cart_cookie,
)
from modellbahn.modules.sales.api.errors import ORDER_NOT_FOUND
from modellbahn.modules.sales.api.schemas import (
    CartLineIn,
    CartOut,
    CheckoutIn,
    OrderOut,
    PaymentIn,
    PaymentProviderOut,
    WithdrawalIn,
    WithdrawalReceiptOut,
)
from modellbahn.modules.sales.application.checkout import Buyer, CheckoutRequest, CheckoutResult
from modellbahn.modules.sales.domain.errors import OrderNotFoundError
from modellbahn.platform.bank import girocode_svg
from modellbahn.platform.config import PaymentProvider, Settings
from modellbahn.platform.errors import problems

router = APIRouter(prefix="/store", tags=["store-sales"])

REPLAY_HEADER = "Idempotent-Replayed"


def _private(response: Response) -> None:
    response.headers["Cache-Control"] = PRIVATE_CACHE_CONTROL


def _answer(result: CheckoutResult, response: Response, settings: Settings) -> OrderOut:
    _private(response)
    if result.replayed:
        response.headers[REPLAY_HEADER] = "true"
    return OrderOut.from_details(result.details, bank=settings.bank_account)


@router.get(
    "/cart",
    operation_id="getCart",
    summary="The visitor's cart at today's prices",
    responses=problems(unsafe=False, validated=False),
)
async def get_cart(cart: CartId, service: CartServiceDep, response: Response) -> CartOut:
    _private(response)
    return CartOut.from_view(await service.view(cart))


@router.put(
    "/cart/lines/{variant_id}",
    operation_id="setCartLine",
    summary="Set how many pieces of a variant are in the cart (0 takes it out)",
    responses=problems({409: ["variant_unavailable", "insufficient_stock", "cart_full"]}),
)
async def set_cart_line(
    variant_id: UUID,
    body: CartLineIn,
    *,
    cart: CartId,
    service: CartServiceDep,
    settings: SettingsDep,
    response: Response,
) -> CartOut:
    """Starts a cart (and sets its cookie) when there is none yet."""
    view = await service.set_quantity(cart, variant_id, body.quantity)
    if view.cart_id is not None and view.cart_id != cart:
        set_cart_cookie(response, view.cart_id, secure=settings.cookie_secure)
    _private(response)
    return CartOut.from_view(view)


@router.delete(
    "/cart/lines/{variant_id}",
    operation_id="removeCartLine",
    summary="Take a variant out of the cart",
    responses=problems(),
)
async def remove_cart_line(
    variant_id: UUID, cart: CartId, service: CartServiceDep, response: Response
) -> CartOut:
    _private(response)
    return CartOut.from_view(await service.set_quantity(cart, variant_id, 0))


@router.post(
    "/checkouts",
    status_code=status.HTTP_201_CREATED,
    operation_id="placeOrder",
    summary="Order what is in the cart; the payment follows",
    responses=problems(
        {
            404: ["address_not_found"],
            409: [
                "cart_empty",
                "cart_items_unavailable",
                "insufficient_stock",
                "price_changed",
                "idempotency_key_reused",
            ],
        },
        rate_limited=True,
    ),
    dependencies=[Depends(limit_checkouts)],
)
async def place_order(
    body: CheckoutIn,
    idempotency_key: IdempotencyKey,
    *,
    cart: CartId,
    customer: OptionalCustomer,
    service: CheckoutServiceDep,
    settings: SettingsDep,
    response: Response,
) -> OrderOut:
    """Prices are taken from the catalogue now, not from what the browser shows; a total
    other than ``expected_total_cents`` orders nothing (409 ``price_changed``). Logged-in
    customers order with their account; guests give an e-mail address. Repeating the
    request with the same ``Idempotency-Key`` returns the same order."""
    request = CheckoutRequest(
        expected_total_cents=body.expected_total_cents,
        email=body.email,
        address=body.address.to_input() if body.address else None,
        address_id=body.address_id,
        save_address=body.save_address,
    )
    buyer = Buyer(account_id=customer.id, email=customer.email) if customer else None
    result = await service.place_order(
        cart_id=cart, request=request, buyer=buyer, idempotency_key=idempotency_key
    )
    return _answer(result, response, settings)


@router.get(
    "/orders/{public_token}",
    operation_id="getOrderByToken",
    summary="An order's status page (the link from the order e-mails)",
    responses=problems(ORDER_NOT_FOUND, unsafe=False),
)
async def get_order(
    public_token: str, service: OrderServiceDep, settings: SettingsDep, response: Response
) -> OrderOut:
    _private(response)
    return OrderOut.from_details(await service.by_token(public_token), bank=settings.bank_account)


@router.get(
    "/orders/{public_token}/girocode.svg",
    operation_id="getOrderGirocode",
    summary="The GiroCode of an order waiting for a bank transfer (SVG for banking apps)",
    response_class=Response,
    responses={
        200: {"content": {"image/svg+xml": {}}, "description": "The GiroCode."},
        **problems(ORDER_NOT_FOUND, unsafe=False, validated=False),
    },
)
async def get_order_girocode(
    public_token: str, service: OrderServiceDep, settings: SettingsDep
) -> Response:
    """Only while the order waits for a transfer; afterwards (or without a bank account) 404."""
    order = (await service.by_token(public_token)).order
    bank = settings.bank_account
    if bank is None or order.awaited_transfer is None:
        raise OrderNotFoundError
    svg = girocode_svg(bank.epc_payload(amount_cents=order.total_cents, reference=order.number))
    return Response(
        content=svg, media_type="image/svg+xml", headers={"Cache-Control": PRIVATE_CACHE_CONTROL}
    )


@router.get(
    "/payment-provider",
    operation_id="getPaymentProvider",
    summary="Who takes the shop's payments: SumUp, the test payment, or nobody",
    responses=problems({}, unsafe=False),
)
async def get_payment_provider(
    service: PaymentServiceDep, settings: SettingsDep
) -> PaymentProviderOut:
    provider = PaymentProvider(service.provider)
    return PaymentProviderOut(
        provider=provider,
        # Without a provider the shop takes no orders at all, transfers included.
        bank_transfer=settings.bank_account is not None and provider is not PaymentProvider.OFF,
    )


@router.post(
    "/orders/{public_token}/payments",
    operation_id="payOrder",
    summary="Pay for an order: on SumUp's page, by bank transfer, or the test payment",
    responses=problems(
        {
            **ORDER_NOT_FOUND,
            409: ["order_not_payable", "idempotency_key_reused", "checkout_closed"],
            503: ["payment_unavailable"],
        },
        rate_limited=True,
    ),
    dependencies=[Depends(limit_checkouts)],
)
async def pay_order(
    public_token: str,
    body: PaymentIn,
    idempotency_key: IdempotencyKey,
    *,
    service: CheckoutServiceDep,
    settings: SettingsDep,
    response: Response,
) -> OrderOut:
    """With SumUp the order comes back with ``payment_url``, the page the customer pays on;
    a page still open is reused. The test payment answers at once: a declined payment is
    recorded, and the order still waits for its payment. A provider failure (503) records
    nothing. A bank transfer (``bank_transfer``, where offered) leaves the order waiting
    ten days, with ``bank_transfer`` saying what to transfer; it closes a SumUp page first.
    Repeating the request with the same ``Idempotency-Key`` never charges twice."""
    result = await service.pay(
        public_token=public_token, method=body.method, idempotency_key=idempotency_key
    )
    return _answer(result, response, settings)


@router.post(
    "/orders/{public_token}/payments/sync",
    operation_id="syncOrderPayment",
    summary="Back from the provider's page: ask it how the payment went",
    responses=problems({**ORDER_NOT_FOUND, 503: ["payment_unavailable"]}, rate_limited=True),
    dependencies=[Depends(limit_checkouts)],
)
async def sync_payment(
    public_token: str, service: PaymentServiceDep, settings: SettingsDep, response: Response
) -> OrderOut:
    """The shop asks the provider itself; what the browser was told on the way back counts
    for nothing. A payment that is still open keeps its ``payment_url``."""
    _private(response)
    return OrderOut.from_details(await service.sync(public_token), bank=settings.bank_account)


@router.post(
    "/withdrawals",
    operation_id="withdrawContract",
    summary="Withdraw from a contract: the shop's withdrawal function (§ 356a BGB)",
    status_code=status.HTTP_201_CREATED,
    responses=problems({}, rate_limited=True),
    dependencies=[Depends(limit_checkouts)],
)
async def withdraw_contract(
    body: WithdrawalIn, service: WithdrawalServiceDep, response: Response
) -> WithdrawalReceiptOut:
    """Takes every declaration, whether or not the number fits an order, and answers the
    same either way; staff judge it. The confirmation of receipt goes out by e-mail at once,
    with what came in and when."""
    _private(response)
    withdrawal = await service.declare(
        name=body.name, order_number=body.order_number, email=body.email, scope=body.scope
    )
    return WithdrawalReceiptOut.from_withdrawal(withdrawal)
