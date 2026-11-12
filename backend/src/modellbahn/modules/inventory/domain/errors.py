"""Errors of the inventory domain. The API layer decides how they are presented."""

from collections.abc import Collection, Mapping
from uuid import UUID


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


class UnitsRefusedError(InventoryError):
    """Of several units, some cannot take part or do not exist, so none did (all or nothing)."""

    def __init__(self, refused: Mapping[str, str], missing: Collection[UUID] = ()) -> None:
        self.refused = dict(sorted(refused.items()))
        """Unit code → state (``picked``, ``shipped`` …)."""
        self.missing = sorted(missing)
        """Ids no unit has."""
        named = [f"{code} ({status})" for code, status in self.refused.items()]
        named += [f"{unit_id} (unknown)" for unit_id in self.missing]
        super().__init__(", ".join(named))


class UnitsNotMovableError(UnitsRefusedError):
    """Units to move that cannot go into a location (picked, shipped, scrapped); none moved."""


class UnitsNotScrappableError(UnitsRefusedError):
    """Units to take out by hand that belong to an order already (picked, shipped); none went."""


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


class PartNotFoundError(InventoryError):
    """The manufacturing module knows no such part."""


class ReceiptNotFoundError(InventoryError):
    pass


class InvalidReceiptStateError(InventoryError):
    """Nothing left to store or write off, or the booking does not belong to the receipt."""


class InsufficientPartsError(InventoryError):
    """Fewer parts in the location (or the store) than are to be taken."""


class BillOfMaterialsMissingError(InventoryError):
    """The variant's product has no bill of materials in its scale: nothing to assemble."""


class ScanNotUndoableError(InventoryError):
    """The scan booked nothing, is too old, was undone already, or its units moved on."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason
