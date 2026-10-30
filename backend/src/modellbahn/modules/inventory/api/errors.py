"""How inventory errors appear in the API: status, problem code and field."""

from collections.abc import Callable, Mapping
from typing import Any, Final

from fastapi import FastAPI

from modellbahn.modules.inventory.domain.errors import (
    BillOfMaterialsMissingError,
    InsufficientPartsError,
    InvalidFieldError,
    InvalidReceiptStateError,
    InvalidUnitStateError,
    LocationCodeTakenError,
    LocationInUseError,
    LocationNotEmptyError,
    LocationNotFoundError,
    OrderNotAllocatableError,
    OrderNotFoundError,
    PartNotFoundError,
    ProductNotFoundError,
    ReceiptNotFoundError,
    ScanIdReusedError,
    ScanNotFoundError,
    ScanNotUndoableError,
    UnitNotFoundError,
    VariantNotFoundError,
)
from modellbahn.platform.errors import (
    AppError,
    ConflictError,
    FieldError,
    NotFoundError,
    ValidationFailedError,
    add_error_translation,
)

STAFF_ACCESS: Final = {401: ["not_authenticated"], 403: ["insufficient_role"]}


def _invalid_field(error: InvalidFieldError) -> AppError:
    return ValidationFailedError(
        [FieldError(field=error.field, code=error.code, message=error.message)]
    )


_TRANSLATIONS: Final[Mapping[type[Exception], Callable[[Any], AppError]]] = {
    InvalidFieldError: _invalid_field,
    LocationNotFoundError: lambda _: NotFoundError(
        "The location does not exist.", code="location_not_found"
    ),
    LocationCodeTakenError: lambda _: ConflictError(
        "Another location already has this code.", code="location_code_taken"
    ),
    LocationNotEmptyError: lambda _: ConflictError(
        "The location holds goods or other locations.", code="location_not_empty"
    ),
    LocationInUseError: lambda _: ConflictError(
        "Goods were stored here; the location keeps its history.", code="location_in_use"
    ),
    UnitNotFoundError: lambda _: NotFoundError("The unit does not exist.", code="unit_not_found"),
    InvalidUnitStateError: lambda error: ConflictError(str(error), code="invalid_unit_state"),
    VariantNotFoundError: lambda _: NotFoundError(
        "The variant does not exist.", code="variant_not_found"
    ),
    OrderNotFoundError: lambda _: NotFoundError(
        "The order does not exist.", code="order_not_found"
    ),
    OrderNotAllocatableError: lambda _: ConflictError(
        "Only paid orders get stock allocated.", code="order_not_allocatable"
    ),
    ProductNotFoundError: lambda _: NotFoundError(
        "The product does not exist.", code="product_not_found"
    ),
    ScanIdReusedError: lambda _: ConflictError(
        "This scan id was used for a different scan.", code="scan_id_reused"
    ),
    ScanNotFoundError: lambda _: NotFoundError("The scan does not exist.", code="scan_not_found"),
    ScanNotUndoableError: lambda error: ConflictError(
        f"The scan cannot be undone: {error.reason}.", code=f"scan_{error.reason}"
    ),
    PartNotFoundError: lambda _: NotFoundError("The part does not exist.", code="part_not_found"),
    ReceiptNotFoundError: lambda _: NotFoundError(
        "The receipt does not exist.", code="receipt_not_found"
    ),
    InvalidReceiptStateError: lambda error: ConflictError(
        f"The receipt does not allow this: {error}.", code="invalid_receipt_state"
    ),
    InsufficientPartsError: lambda _: ConflictError(
        "Not enough parts in stock for this.", code="parts_missing"
    ),
    BillOfMaterialsMissingError: lambda _: ConflictError(
        "The product has no bill of materials in this scale.", code="no_bill_of_materials"
    ),
}


def install_error_translations(app: FastAPI) -> None:
    """Answer the inventory domain errors with their problem responses."""
    for error_type, translate in _TRANSLATIONS.items():
        add_error_translation(app, error_type, translate)
