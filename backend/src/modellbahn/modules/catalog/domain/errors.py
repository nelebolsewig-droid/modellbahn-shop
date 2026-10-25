"""Errors of the catalogue domain. The API layer decides how they are presented."""

from enum import StrEnum


class CatalogError(Exception):
    """Base of every error raised by the catalogue module."""


class InvalidFieldError(CatalogError):
    """A value breaks a rule of the model (length, format, range)."""

    def __init__(self, field: str, code: str, message: str) -> None:
        super().__init__(f"{field}: {message}")
        self.field = field
        self.code = code
        self.message = message


class UnknownReferenceError(InvalidFieldError):
    """A code or id names nothing: an unknown scale, finish, epoch, category or image."""

    def __init__(self, field: str, value: object) -> None:
        super().__init__(field, "unknown", f"{value!r} does not exist")


class ProductNotFoundError(CatalogError):
    pass


class ProductScaleNotFoundError(CatalogError):
    pass


class VariantNotFoundError(CatalogError):
    pass


class CategoryNotFoundError(CatalogError):
    pass


class ScaleNotFoundError(CatalogError):
    pass


class ScaleInUseError(CatalogError):
    """A product is offered in the scale, or a photo is tagged with it."""


class SlugTakenError(CatalogError):
    """Another product or category already uses the address."""


class SlugLockedError(CatalogError):
    """The address of a product that has been published is fixed: links point to it."""


class ScaleAlreadyAddedError(CatalogError):
    """The product already comes in this scale."""


class VariantAlreadyExistsError(CatalogError):
    """The scale is already sold in this finish."""


class InvalidProductStateError(CatalogError):
    """The product's state does not allow this (e.g. archiving a draft)."""


class VariantHasUnitsError(CatalogError):
    """The workshop has (or had) units of the variant; it can be deactivated, not removed."""


class ProductNotDeletableError(CatalogError):
    """Only drafts that were never published can be deleted."""


class VersionMismatchError(CatalogError):
    """The product changed since the client read it (``If-Match`` names another version)."""


class CategoryCycleError(CatalogError):
    """A category cannot be moved below itself or one of its subcategories."""


class PublishBlocker(StrEnum):
    """Why a product cannot be (or stay) in the shop."""

    NO_CATEGORY = "no_category"
    NO_ACTIVE_VARIANT = "no_active_variant"
    NO_MAIN_IMAGE = "no_main_image"
    MAIN_IMAGE_NOT_READY = "main_image_not_ready"


class ProductNotPublishableError(CatalogError):
    """Publishing (or a change to a published product) would break a rule of the shop."""

    def __init__(self, blockers: list[PublishBlocker]) -> None:
        super().__init__("not publishable: " + ", ".join(blockers))
        self.blockers = blockers
