"""Errors of the inventory domain. The API layer decides how they are presented."""


class InventoryError(Exception):
    """Base of every error raised by the inventory module."""


class InvalidFieldError(InventoryError):
    """A value breaks a rule of the model (length, format, range)."""

    def __init__(self, field: str, code: str, message: str) -> None:
        super().__init__(f"{field}: {message}")
        self.field = field
        self.code = code
        self.message = message


class LocationNotFoundError(InventoryError):
    pass


class LocationCodeTakenError(InventoryError):
    """Another location already has this code; codes are printed on labels, so unique."""


class LocationNotEmptyError(InventoryError):
    """A location with sub-locations or goods in it cannot be removed."""


class LocationInUseError(InventoryError):
    """The journal refers to the location: it keeps its history and cannot be removed."""


class UnitNotFoundError(InventoryError):
    pass


class InvalidUnitStateError(InventoryError):
    """The unit's state does not allow this (e.g. scrapping a shipped unit)."""


class VariantNotFoundError(InventoryError):
    """The catalogue knows no such variant."""


class OrderNotFoundError(InventoryError):
    pass


class ProductNotFoundError(InventoryError):
    """No product with this address is in the shop."""


class OrderNotAllocatableError(InventoryError):
    """Only paid orders get stock allocated."""


class ScanIdReusedError(InventoryError):
    """The scan id was already used for a different scan."""


class ScanNotFoundError(InventoryError):
    pass


class ScanNotUndoableError(InventoryError):
    """The scan booked nothing, is too old, was undone already, or its units moved on."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason
