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


class InsufficientStockError(SalesError):
    """Not enough on the shelves, and the variant is not made to order."""

    def __init__(self, variants: dict[UUID, int]) -> None:
        super().__init__(
            "not enough in stock: " + ", ".join(f"{v} ({n} left)" for v, n in variants.items())
        )
        self.variants = dict(variants)
        """Free units per variant that is short."""


class OrderNotPickedError(SalesError):
    """Only an order whose pieces are all picked can be shipped."""

    def __init__(self, *, picked: int, total: int) -> None:
        super().__init__(f"{picked} of {total} pieces picked")
        self.picked = picked
        self.total = total


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


class MarketplaceOrderError(SalesError):
    """A marketplace order is cancelled where it was bought; the shop follows."""


class PaymentUnavailableError(SalesError):
    """The payment provider could not be reached or failed; nothing was charged."""


class RefundRejectedError(SalesError):
    """The payment provider answered and refused the refund; nothing went back.

    ``reason`` is the provider's own words (status and message), for the staff to read.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(f"the payment provider refused the refund: {reason}")
        self.reason = reason


class RefundNotPossibleError(SalesError):
    """Nothing (or less than asked) is left to refund, or the order was never paid."""

    def __init__(self, refundable_cents: int) -> None:
        super().__init__(f"at most {refundable_cents} cents can be refunded")
        self.refundable_cents = refundable_cents


class CheckoutClosedError(SalesError):
    """No payment provider is connected (MB_PAYMENT_PROVIDER=off): the shop takes no orders."""


class AddressNotFoundError(SalesError):
    pass


class AddressBookFullError(SalesError):
    """An address book holds a limited number of addresses."""


class LabelNotFoundError(SalesError):
    """The order has no shipping label in force."""


class LabelExistsError(SalesError):
    """The order has a label in force already; cancel it before booking another."""


class CarrierUnavailableError(SalesError):
    """No carrier is connected, or it could not be reached; nothing was booked."""


class CarrierRejectedError(SalesError):
    """The carrier answered and refused, e.g. an address it cannot deliver to.

    ``reason`` is the carrier's own words, for the staff to read and fix.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(f"the carrier refused: {reason}")
        self.reason = reason
