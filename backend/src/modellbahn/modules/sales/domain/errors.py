"""Errors of the sales domain. The API layer decides how they are presented."""

from collections.abc import Collection
from uuid import UUID


class SalesError(Exception):
    """Base of every error raised by the sales module."""


class InvalidFieldError(SalesError):
    """A value breaks a rule of the model (length, format, range)."""

    def __init__(self, field: str, code: str, message: str) -> None:
        super().__init__(f"{field}: {message}")
        self.field = field
        self.code = code
        self.message = message


class VariantUnavailableError(SalesError):
    """The variant is unknown or not for sale (inactive, or its product left the shop)."""

    def __init__(self, variant_id: UUID) -> None:
        super().__init__(f"variant {variant_id} cannot be bought")
        self.variant_id = variant_id


class CartFullError(SalesError):
    """A cart holds a limited number of different variants."""


class EmptyCartError(SalesError):
    """There is nothing in the cart to order."""


class CartItemsUnavailableError(SalesError):
    """Some variants in the cart can no longer be bought; they must be removed first."""

    def __init__(self, variant_ids: Collection[UUID]) -> None:
        super().__init__("unavailable: " + ", ".join(str(v) for v in variant_ids))
        self.variant_ids = list(variant_ids)


class PriceChangedError(SalesError):
    """The total the customer confirmed is no longer the total of the cart."""

    def __init__(self, *, expected_cents: int, actual_cents: int) -> None:
        super().__init__(f"expected {expected_cents} ct, the cart now costs {actual_cents} ct")
        self.expected_cents = expected_cents
        self.actual_cents = actual_cents


class IdempotencyKeyReusedError(SalesError):
    """The key was already used for a different request."""


class OrderNotFoundError(SalesError):
    pass


class OrderNotPayableError(SalesError):
    """Only orders that wait for their payment can be paid."""


class InvalidOrderStateError(SalesError):
    """The order's state does not allow this (e.g. shipping an unpaid order)."""


class PaymentUnavailableError(SalesError):
    """The payment provider could not be reached or failed; nothing was charged."""


class AddressNotFoundError(SalesError):
    pass


class AddressBookFullError(SalesError):
    """An address book holds a limited number of addresses."""
