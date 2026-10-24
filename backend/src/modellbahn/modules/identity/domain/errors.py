"""Errors of the identity domain. The API layer decides how they are presented."""

from enum import StrEnum


class IdentityError(Exception):
    """Base of every error raised by the identity module."""


class PasswordRule(StrEnum):
    """The password policy rule a password broke."""

    TOO_SHORT = "too_short"
    TOO_LONG = "too_long"
    EQUALS_EMAIL = "equals_email"


class PasswordPolicyViolationError(IdentityError):
    """A new password does not satisfy the password policy."""

    def __init__(self, rule: PasswordRule) -> None:
        super().__init__(f"password violates the policy: {rule}")
        self.rule = rule


class InvalidDisplayNameError(IdentityError):
    """A display name is empty, too long or contains control characters."""


class InvalidCredentialsError(IdentityError):
    """Login failed. Deliberately says nothing about why (unknown, wrong or locked)."""


class EmailNotVerifiedError(IdentityError):
    """The password was right, but the customer has not confirmed the e-mail address yet."""


class InvalidTokenError(IdentityError):
    """A verification or reset token is unknown, expired, already used or for something else."""


class NotAuthenticatedError(IdentityError):
    """No valid session for the requested area."""


class InvalidPasswordError(IdentityError):
    """The password confirming a sensitive action was wrong (e.g. deletion, verification)."""


class AccountAlreadyExistsError(IdentityError):
    """An account of this kind already uses the e-mail address."""


class AccountNotFoundError(IdentityError):
    """No account of this kind uses the e-mail address (used by the server's CLI only)."""
