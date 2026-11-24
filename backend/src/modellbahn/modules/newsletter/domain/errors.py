"""Errors of the newsletter module; the API turns them into problem responses."""


class NewsletterError(Exception):
    """Base class of the newsletter module's domain errors."""


class NewsletterTokenInvalidError(NewsletterError):
    """The confirmation link is unknown, already used or expired."""


class EmailNotVerifiedError(NewsletterError):
    """The account's address is not verified yet: no newsletter before that."""
