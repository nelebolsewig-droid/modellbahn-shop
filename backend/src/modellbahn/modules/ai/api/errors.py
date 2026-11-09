"""How AI errors appear in the API: status, problem code and field."""

from collections.abc import Callable, Mapping
from typing import Any, Final

from fastapi import FastAPI

from modellbahn.modules.ai.domain.errors import (
    AiDisabledError,
    InvalidFieldError,
    ProductNotFoundError,
    RunNotFoundError,
    RunNotReviewableError,
)
from modellbahn.platform.errors import (
    AppError,
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
    AiDisabledError: lambda _: ConflictError(
        "No language model is configured for product texts.", code="ai_disabled"
    ),
    ProductNotFoundError: lambda _: NotFoundError(
        "The product does not exist.", code="product_not_found"
    ),
    RunNotFoundError: lambda _: NotFoundError(
        "The text draft does not exist.", code="ai_run_not_found"
    ),
    RunNotReviewableError: lambda error: ConflictError(
        f"The draft cannot be taken over: {error.reason}.", code="ai_run_not_reviewable"
    ),
}


def install_error_translations(app: FastAPI) -> None:
    """Answer the AI domain errors with their problem responses."""
    for error_type, translate in _TRANSLATIONS.items():
        add_error_translation(app, error_type, translate)
