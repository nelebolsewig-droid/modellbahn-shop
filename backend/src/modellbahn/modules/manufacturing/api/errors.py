"""How manufacturing errors appear in the API: status, problem code and field."""

from collections.abc import Callable, Mapping
from typing import Any, Final

from fastapi import FastAPI

from modellbahn.modules.manufacturing.domain.errors import (
    InvalidFieldError,
    InvalidPrintJobStateError,
    MaterialInUseError,
    MaterialNotFoundError,
    PartInUseError,
    PartNotFoundError,
    PrinterInUseError,
    PrinterNotFoundError,
    PrinterUnavailableError,
    PrintJobNotFoundError,
    ProductScaleNotFoundError,
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

PRINTER_UNAVAILABLE: Final = [
    "printer_busy",
    "printer_not_in_service",
    "printer_retired",
    "printer_has_queue",
]
"""Problem codes of :class:`PrinterUnavailableError`, one per reason."""


def _invalid_field(error: InvalidFieldError) -> AppError:
    return ValidationFailedError(
        [FieldError(field=error.field, code=error.code, message=error.message)]
    )


_TRANSLATIONS: Final[Mapping[type[Exception], Callable[[Any], AppError]]] = {
    InvalidFieldError: _invalid_field,
    PrinterNotFoundError: lambda _: NotFoundError(
        "The printer does not exist.", code="printer_not_found"
    ),
    PrinterInUseError: lambda _: ConflictError(
        "The printer has print jobs; it keeps its history and can be retired.",
        code="printer_in_use",
    ),
    PrinterUnavailableError: lambda error: ConflictError(
        f"The printer is unavailable: {error.reason}.", code=f"printer_{error.reason}"
    ),
    MaterialNotFoundError: lambda _: NotFoundError(
        "The material does not exist.", code="material_not_found"
    ),
    MaterialInUseError: lambda _: ConflictError(
        "Parts are made of this material; it can be archived.", code="material_in_use"
    ),
    PartNotFoundError: lambda _: NotFoundError("The part does not exist.", code="part_not_found"),
    PartInUseError: lambda _: ConflictError(
        "A kit needs the part or it was printed; it can be archived.", code="part_in_use"
    ),
    ProductScaleNotFoundError: lambda _: NotFoundError(
        "The product is not offered in this scale.", code="product_scale_not_found"
    ),
    PrintJobNotFoundError: lambda _: NotFoundError(
        "The print job does not exist.", code="print_job_not_found"
    ),
    InvalidPrintJobStateError: lambda error: ConflictError(
        f"Not possible while the job is {error.status}.", code="invalid_print_job_state"
    ),
}


def install_error_translations(app: FastAPI) -> None:
    """Answer the manufacturing domain errors with their problem responses."""
    for error_type, translate in _TRANSLATIONS.items():
        add_error_translation(app, error_type, translate)
