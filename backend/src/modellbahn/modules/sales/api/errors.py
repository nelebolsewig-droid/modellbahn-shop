"""How sales errors appear in the API: status, problem code and field."""

from collections.abc import Callable, Mapping
from typing import Any, Final

from fastapi import FastAPI

from modellbahn.modules.sales.domain.errors import (
    AddressBookFullError,
    AddressNotFoundError,
    CartFullError,
    CartItemsUnavailableError,
    EmptyCartError,
    IdempotencyKeyReusedError,
    InsufficientStockError,
    InvalidFieldError,
    InvalidOrderStateError,
    OrderNotFoundError,
    OrderNotPayableError,
    OrderNotPickedError,
    PaymentUnavailableError,
    PriceChangedError,
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


_TRANSLATIONS: Final[Mapping[type[Exception], Callable[[Any], AppError]]] = {
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
    AddressNotFoundError: lambda _: NotFoundError(
        "The address does not exist.", code="address_not_found"
    ),
    AddressBookFullError: lambda _: ConflictError(
        "The address book is full; remove an address first.", code="address_book_full"
    ),
}


def install_error_translations(app: FastAPI) -> None:
    """Answer the sales domain errors with their problem responses."""
    for error_type, translate in _TRANSLATIONS.items():
        add_error_translation(app, error_type, translate)
