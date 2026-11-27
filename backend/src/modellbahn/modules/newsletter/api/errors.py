"""How newsletter errors appear in the API: status and problem code."""

from collections.abc import Callable, Mapping
from typing import Any, Final

from fastapi import FastAPI

from modellbahn.modules.newsletter.domain.errors import NewsletterTokenInvalidError
from modellbahn.platform.errors import AppError, BadRequestError, add_error_translation

STAFF_ACCESS: Final = {401: ["not_authenticated"], 403: ["insufficient_role"]}

_TRANSLATIONS: Final[Mapping[type[Exception], Callable[[Any], AppError]]] = {
    NewsletterTokenInvalidError: lambda _: BadRequestError(
        "The link is unknown, used or expired.", code="newsletter_token_invalid"
    ),
}


def install_error_translations(app: FastAPI) -> None:
    """Answer the newsletter's domain errors with their problem responses."""
    for error_type, translate in _TRANSLATIONS.items():
        add_error_translation(app, error_type, translate)
