"""How site errors appear in the API: status, problem code and field."""

from collections.abc import Callable, Mapping
from typing import Any, Final

from fastapi import FastAPI

from modellbahn.modules.site.domain.errors import (
    FairNotAnnounceableError,
    FairNotFoundError,
    InvalidFieldError,
    SubscriptionTokenInvalidError,
)
from modellbahn.platform.errors import (
    AppError,
    BadRequestError,
    ConflictError,
    FieldError,
    NotFoundError,
    ValidationFailedError,
    add_error_translation,
)

STAFF_ACCESS: Final = {401: ["not_authenticated"], 403: ["insufficient_role"]}


def _invalid_field(error: InvalidFieldError) -> AppError:
    return ValidationFailedError(
        [FieldError(field=error.field, code=error.code, message=error.message)]
    )


_TRANSLATIONS: Final[Mapping[type[Exception], Callable[[Any], AppError]]] = {
    InvalidFieldError: _invalid_field,
    FairNotFoundError: lambda _: NotFoundError("The fair does not exist.", code="fair_not_found"),
    FairNotAnnounceableError: lambda error: ConflictError(
        f"The fair cannot be announced: {error.reason}.", code=f"fair_{error.reason}"
    ),
    SubscriptionTokenInvalidError: lambda _: BadRequestError(
        "The link is unknown, used or expired.", code="fair_news_token_invalid"
    ),
}


def install_error_translations(app: FastAPI) -> None:
    """Answer the site domain errors with their problem responses."""
    for error_type, translate in _TRANSLATIONS.items():
        add_error_translation(app, error_type, translate)
