"""Errors of the site module; the API turns them into problem responses."""


class SiteError(Exception):
    """Base class of the site module's domain errors."""


class InvalidFieldError(SiteError):
    """A value breaks a rule of the model (length, format, range)."""

    def __init__(self, field: str, code: str, message: str) -> None:
        super().__init__(f"{field}: {message}")
        self.field = field
        self.code = code
        self.message = message


class FairNotFoundError(SiteError):
    """No such fair, or (in the shop) not published."""


class FairNotAnnounceableError(SiteError):
    """The fair cannot be announced: ``not_published``, ``past`` or ``already_announced``."""

    def __init__(self, reason: str) -> None:
        super().__init__(f"the fair cannot be announced: {reason}")
        self.reason = reason


class SubscriptionTokenInvalidError(SiteError):
    """The confirmation link is unknown, already used or expired."""
