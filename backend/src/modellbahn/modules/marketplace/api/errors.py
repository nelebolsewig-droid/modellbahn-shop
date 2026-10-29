"""How marketplace errors appear in the API: status, problem code and field."""

from collections.abc import Callable, Mapping
from typing import Any, Final

from fastapi import FastAPI

from modellbahn.modules.marketplace.application.ports import (
    MarketplaceRejectedError,
    MarketplaceUnavailableError,
)
from modellbahn.modules.marketplace.domain.errors import (
    AccountNotReadyError,
    ConnectionStateInvalidError,
    InvalidFieldError,
    ListingNotFoundError,
    MarketplaceOrderNotFoundError,
    NotConnectedError,
    TestModeOnlyError,
)
from modellbahn.platform.errors import (
    AppError,
    BadRequestError,
    ConflictError,
    FieldError,
    NotFoundError,
    ServiceUnavailableError,
    ValidationFailedError,
    add_error_translation,
)

STAFF_ACCESS: Final = {401: ["not_authenticated"], 403: ["insufficient_role"]}
EBAY_OFF: Final = "ebay_off"
EBAY_UNAVAILABLE: Final = {503: ["ebay_unavailable"]}


def _invalid_field(error: InvalidFieldError) -> AppError:
    return ValidationFailedError(
        [FieldError(field=error.field, code=error.code, message=error.message)]
    )


_TRANSLATIONS: Final[Mapping[type[Exception], Callable[[Any], AppError]]] = {
    InvalidFieldError: _invalid_field,
    NotConnectedError: lambda _: ConflictError(
        "No eBay account is connected (or its consent ran out).", code="ebay_not_connected"
    ),
    AccountNotReadyError: lambda error: ConflictError(
        f"Offers cannot go up on eBay yet: {', '.join(error.blockers)}.", code="ebay_not_ready"
    ),
    ConnectionStateInvalidError: lambda _: BadRequestError(
        "The answer from eBay does not belong to a connection started here.",
        code="ebay_state_invalid",
    ),
    ListingNotFoundError: lambda _: NotFoundError(
        "The listing (or the product in that scale) does not exist.", code="listing_not_found"
    ),
    MarketplaceOrderNotFoundError: lambda _: NotFoundError(
        "The eBay order does not exist.", code="marketplace_order_not_found"
    ),
    TestModeOnlyError: lambda _: ConflictError(
        "Only the built-in test marketplace takes test sales.", code="test_mode_only"
    ),
    MarketplaceUnavailableError: lambda _: ServiceUnavailableError(
        "eBay cannot be reached right now; please try again shortly.", code="ebay_unavailable"
    ),
    MarketplaceRejectedError: lambda error: ConflictError(
        f"eBay refused: {error.message or error.code}", code="ebay_rejected"
    ),
}


def install_error_translations(app: FastAPI) -> None:
    """Answer the marketplace errors with their problem responses."""
    for error_type, translate in _TRANSLATIONS.items():
        add_error_translation(app, error_type, translate)
