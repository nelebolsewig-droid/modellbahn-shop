"""How sales errors appear in the API: status, problem code and field."""

from collections.abc import Callable, Mapping
from typing import Any, Final

from fastapi import FastAPI

from modellbahn.modules.sales.domain.errors import (
    AddressBookFullError,
    AddressNotFoundError,
    CarrierRejectedError,
    CarrierUnavailableError,
    CartFullError,
    CartItemsUnavailableError,
    CheckoutClosedError,
    EmptyCartError,
    IdempotencyKeyReusedError,
    InsufficientStockError,
    InvalidFieldError,
    InvalidOrderStateError,
    LabelExistsError,
    LabelNotFoundError,
    MarketplaceOrderError,
    OrderNotFoundError,
    OrderNotPayableError,
    OrderNotPickedError,
    PaymentUnavailableError,
    PriceChangedError,
    RefundNotPossibleError,
    RefundRejectedError,
    VariantUnavailableError,
)
from modellbahn.platform.errors import (
    AppError,
    ConflictError,
    FieldError,
    NotFoundError,
    ServiceUnavailableError,
    ValidationFailedError,
    add_error_translation,
)

STAFF_ACCESS: Final = {401: ["not_authenticated"], 403: ["insufficient_role"]}
CUSTOMER_ACCESS: Final = {401: ["not_authenticated"]}
ORDER_NOT_FOUND: Final = {404: ["order_not_found"]}

# Retry a failed payment provider after this many seconds.
_PAYMENT_RETRY_AFTER: Final = "30"


def _invalid_field(error: InvalidFieldError) -> AppError:
    return ValidationFailedError(
        [FieldError(field=error.field, code=error.code, message=error.message)]
    )


def _price_changed(error: PriceChangedError) -> AppError:
    return ConflictError(
        f"The cart now costs {error.actual_cents} cents instead of {error.expected_cents}; "
        "review it again.",
        code="price_changed",
    )


def _refund_not_possible(error: RefundNotPossibleError) -> AppError:
    return ConflictError(
        f"At most {error.refundable_cents} cents can still be refunded for this order.",
        code="refund_not_possible",
    )


_TRANSLATIONS: Final[Mapping[type[Exception], Callable[[Any], AppError]]] = {
    RefundNotPossibleError: _refund_not_possible,
    CarrierUnavailableError: lambda _: ServiceUnavailableError(
        "The carrier is not connected or not reachable; no label was booked.",
        code="carrier_unavailable",
    ),
    # The detail is the carrier's own answer, e.g. an address it cannot deliver to.
    CarrierRejectedError: lambda error: ConflictError(error.reason, code="carrier_rejected"),
    LabelExistsError: lambda _: ConflictError(
        "The order has a shipping label already; cancel it to book another.",
        code="label_exists",
    ),
    LabelNotFoundError: lambda _: NotFoundError(
        "The order has no shipping label in force.", code="label_not_found"
    ),
    # The detail is the provider's own answer: the Stellwerk shows it to the staff.
    RefundRejectedError: lambda error: ConflictError(error.reason, code="refund_rejected"),
    InvalidFieldError: _invalid_field,
    PriceChangedError: _price_changed,
    VariantUnavailableError: lambda _: ConflictError(
        "This variant cannot be bought.", code="variant_unavailable"
    ),
    CartFullError: lambda _: ConflictError(
        "The cart holds no more different articles.", code="cart_full"
    ),
    EmptyCartError: lambda _: ConflictError("The cart is empty.", code="cart_empty"),
    InsufficientStockError: lambda _: ConflictError(
        "Not enough in stock, and the article is not made to order.", code="insufficient_stock"
    ),
    OrderNotPickedError: lambda error: ConflictError(
        f"Only {error.picked} of {error.total} pieces are picked; pick the order first.",
        code="order_not_picked",
    ),
    CartItemsUnavailableError: lambda _: ConflictError(
        "Some articles in the cart can no longer be bought; remove them first.",
        code="cart_items_unavailable",
    ),
    IdempotencyKeyReusedError: lambda _: ConflictError(
        "This Idempotency-Key was used for a different request.", code="idempotency_key_reused"
    ),
    OrderNotFoundError: lambda _: NotFoundError(
        "The order does not exist.", code="order_not_found"
    ),
    OrderNotPayableError: lambda _: ConflictError(
        "The order is not waiting for a payment.", code="order_not_payable"
    ),
    InvalidOrderStateError: lambda error: ConflictError(str(error), code="invalid_order_state"),
    PaymentUnavailableError: lambda _: ServiceUnavailableError(
        "The payment provider is not available; nothing was charged. Try again shortly.",
        code="payment_unavailable",
        headers={"Retry-After": _PAYMENT_RETRY_AFTER},
    ),
    CheckoutClosedError: lambda _: ConflictError(
        "The shop takes no orders yet: no payment provider is connected.",
        code="checkout_closed",
    ),
    AddressNotFoundError: lambda _: NotFoundError(
        "The address does not exist.", code="address_not_found"
    ),
    AddressBookFullError: lambda _: ConflictError(
        "The address book is full; remove an address first.", code="address_book_full"
    ),
    MarketplaceOrderError: lambda _: ConflictError(
        "The order came from a marketplace; cancel it there.", code="marketplace_order"
    ),
}


def install_error_translations(app: FastAPI) -> None:
    """Answer the sales domain errors with their problem responses."""
    for error_type, translate in _TRANSLATIONS.items():
        add_error_translation(app, error_type, translate)
