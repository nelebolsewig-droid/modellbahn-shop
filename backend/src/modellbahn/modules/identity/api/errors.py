"""How identity errors appear in the API: status, problem code and documentation."""

from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from typing import Any, Final

from fastapi import FastAPI

from modellbahn.modules.identity.domain.errors import (
    EmailNotVerifiedError,
    InvalidCredentialsError,
    InvalidDisplayNameError,
    InvalidPasswordError,
    InvalidTokenError,
    NotAuthenticatedError,
    PasswordPolicyViolationError,
    PasswordRule,
)
from modellbahn.platform.errors import (
    AppError,
    BadRequestError,
    FieldError,
    ForbiddenError,
    UnauthorizedError,
    ValidationFailedError,
    add_error_translation,
)

_PASSWORD_RULE_MESSAGES: Final = {
    PasswordRule.TOO_SHORT: "The password is too short.",
    PasswordRule.TOO_LONG: "The password is too long.",
    PasswordRule.EQUALS_EMAIL: "The password must not be the e-mail address.",
}


def password_policy_problem(
    error: PasswordPolicyViolationError, field: str
) -> ValidationFailedError:
    return ValidationFailedError(
        [
            FieldError(
                field=field, code=error.rule.value, message=_PASSWORD_RULE_MESSAGES[error.rule]
            )
        ]
    )


@contextmanager
def password_field(field: str) -> Iterator[None]:
    """Report password policy violations as validation errors of the body field ``field``."""
    try:
        yield
    except PasswordPolicyViolationError as exc:
        raise password_policy_problem(exc, field) from exc


_TRANSLATIONS: Final[Mapping[type[Exception], Callable[[Any], AppError]]] = {
    InvalidCredentialsError: lambda _: UnauthorizedError(
        "The e-mail address or the password is wrong.", code="invalid_credentials"
    ),
    EmailNotVerifiedError: lambda _: ForbiddenError(
        "The e-mail address has not been verified yet.", code="email_not_verified"
    ),
    InvalidTokenError: lambda _: BadRequestError(
        "The link is invalid, expired or has already been used.", code="invalid_token"
    ),
    InvalidPasswordError: lambda _: BadRequestError(
        "The password is wrong.", code="invalid_password"
    ),
    NotAuthenticatedError: lambda _: UnauthorizedError(
        "You are not logged in.", code="not_authenticated"
    ),
    InvalidDisplayNameError: lambda _: ValidationFailedError(
        [FieldError(field="display_name", code="invalid", message="The display name is invalid.")]
    ),
    PasswordPolicyViolationError: lambda error: password_policy_problem(error, "password"),
}


def install_error_translations(app: FastAPI) -> None:
    """Answer the identity domain errors with their problem responses."""
    for error_type, translate in _TRANSLATIONS.items():
        add_error_translation(app, error_type, translate)
