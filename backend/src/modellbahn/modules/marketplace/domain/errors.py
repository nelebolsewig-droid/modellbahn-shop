"""Errors of the marketplace module; the API turns them into problem responses."""


class MarketplaceError(Exception):
    """Base class of the marketplace module's domain errors."""


class InvalidFieldError(MarketplaceError):
    """A value breaks a rule of the model (range, format)."""

    def __init__(self, field: str, code: str, message: str) -> None:
        super().__init__(f"{field}: {message}")
        self.field = field
        self.code = code
        self.message = message


class NotConnectedError(MarketplaceError):
    """The shop has no eBay account connected (or its consent ran out)."""


class AccountNotReadyError(MarketplaceError):
    """Connected, but offers cannot go up yet: policies or the location are missing."""

    def __init__(self, blockers: list[str]) -> None:
        super().__init__(", ".join(blockers))
        self.blockers = blockers


class ConnectionStateInvalidError(MarketplaceError):
    """The answer from eBay's consent page does not belong to a connection we started."""


class ListingNotFoundError(MarketplaceError):
    """No such listing, or the product (in that scale) it would offer does not exist."""


class MarketplaceOrderNotFoundError(MarketplaceError):
    pass


class TestModeOnlyError(MarketplaceError):
    """Only the built-in test marketplace takes test sales."""
