"""How catalogue errors appear in the API: status, problem code and field."""

from collections.abc import Callable, Mapping
from typing import Any, Final

from fastapi import FastAPI

from modellbahn.modules.catalog.domain.errors import (
    CategoryCycleError,
    CategoryNotFoundError,
    InvalidFieldError,
    InvalidProductStateError,
    ProductNotDeletableError,
    ProductNotFoundError,
    ProductNotPublishableError,
    ProductScaleNotFoundError,
    PublishBlocker,
    ScaleAlreadyAddedError,
    ScaleInUseError,
    ScaleNotFoundError,
    SlugLockedError,
    SlugTakenError,
    VariantAlreadyExistsError,
    VariantNotFoundError,
    VersionMismatchError,
)
from modellbahn.platform.errors import (
    AppError,
    ConflictError,
    FieldError,
    NotFoundError,
    PreconditionFailedError,
    ValidationFailedError,
    add_error_translation,
)

_BLOCKER_MESSAGES: Final = {
    PublishBlocker.NO_CATEGORY: "The product needs a category.",
    PublishBlocker.NO_ACTIVE_VARIANT: "The product needs at least one active variant.",
    PublishBlocker.NO_MAIN_IMAGE: "The product needs a main image.",
    PublishBlocker.MAIN_IMAGE_NOT_READY: "The main image is still being processed.",
}

ACCESS: Final = {401: ["not_authenticated"], 403: ["insufficient_role"]}
PRODUCT_NOT_FOUND: Final = {404: ["product_not_found"]}
VERSIONED: Final = {412: ["precondition_failed"]}
VERSION_REQUIRED: Final = {412: ["precondition_failed"], 428: ["precondition_required"]}


def _not_publishable(error: ProductNotPublishableError) -> AppError:
    return ValidationFailedError(
        [
            FieldError(field="product", code=blocker.value, message=_BLOCKER_MESSAGES[blocker])
            for blocker in error.blockers
        ],
        "The product cannot be in the shop like this.",
        code="not_publishable",
    )


def _invalid_field(error: InvalidFieldError) -> AppError:
    return ValidationFailedError(
        [FieldError(field=error.field, code=error.code, message=error.message)]
    )


_TRANSLATIONS: Final[Mapping[type[Exception], Callable[[Any], AppError]]] = {
    InvalidFieldError: _invalid_field,
    ProductNotPublishableError: _not_publishable,
    CategoryCycleError: lambda _: ValidationFailedError(
        [
            FieldError(
                field="parent_id",
                code="cycle",
                message="A category cannot be placed below itself.",
            )
        ]
    ),
    ProductNotFoundError: lambda _: NotFoundError(
        "The product does not exist.", code="product_not_found"
    ),
    ProductScaleNotFoundError: lambda _: NotFoundError(
        "The scale of the product does not exist.", code="product_scale_not_found"
    ),
    VariantNotFoundError: lambda _: NotFoundError(
        "The variant does not exist.", code="variant_not_found"
    ),
    CategoryNotFoundError: lambda _: NotFoundError(
        "The category does not exist.", code="category_not_found"
    ),
    ScaleNotFoundError: lambda _: NotFoundError(
        "The scale does not exist.", code="scale_not_found"
    ),
    ScaleInUseError: lambda _: ConflictError(
        "Products are offered in this scale or photos are tagged with it.", code="scale_in_use"
    ),
    SlugTakenError: lambda _: ConflictError("The address is already used.", code="slug_taken"),
    SlugLockedError: lambda _: ConflictError(
        "A product that has been published keeps its address.", code="slug_locked"
    ),
    ScaleAlreadyAddedError: lambda _: ConflictError(
        "The product already comes in this scale.", code="scale_exists"
    ),
    VariantAlreadyExistsError: lambda _: ConflictError(
        "This scale is already sold in this finish.", code="variant_exists"
    ),
    InvalidProductStateError: lambda error: ConflictError(str(error), code="invalid_product_state"),
    ProductNotDeletableError: lambda _: ConflictError(
        "Only drafts that were never published can be deleted.", code="product_not_deletable"
    ),
    VersionMismatchError: lambda _: PreconditionFailedError(
        "The product was changed in the meantime; load it again.", code="precondition_failed"
    ),
}


def install_error_translations(app: FastAPI) -> None:
    """Answer the catalogue domain errors with their problem responses."""
    for error_type, translate in _TRANSLATIONS.items():
        add_error_translation(app, error_type, translate)
