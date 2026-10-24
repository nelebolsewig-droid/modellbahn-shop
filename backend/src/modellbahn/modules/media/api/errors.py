"""How media errors appear in the API: status and problem code."""

from collections.abc import Callable, Mapping
from typing import Any, Final

from fastapi import FastAPI

from modellbahn.modules.media.domain.errors import (
    AssetInUseError,
    AssetNotFoundError,
    InvalidAssetStateError,
    UploadMissingError,
    UploadRejectedError,
    UploadRule,
    UploadSizeMismatchError,
)
from modellbahn.platform.errors import (
    AppError,
    ConflictError,
    FieldError,
    NotFoundError,
    ValidationFailedError,
    add_error_translation,
)

_UPLOAD_RULE_MESSAGES: Final = {
    UploadRule.UNSUPPORTED_KIND: "Only images can be uploaded so far.",
    UploadRule.UNSUPPORTED_TYPE: "Images must be JPEG, PNG, WebP, AVIF or HEIC.",
    UploadRule.EMPTY: "The file is empty.",
    UploadRule.TOO_LARGE: "The file is larger than 50 MiB.",
    UploadRule.INVALID_CHECKSUM: "The checksum must be a SHA-256 hex digest.",
    UploadRule.INVALID_FILENAME: "The file name is empty or too long.",
}

NOT_FOUND: Final = {404: ["asset_not_found"]}
ACCESS: Final = {401: ["not_authenticated"], 403: ["insufficient_role"]}


def _upload_rejected(error: UploadRejectedError) -> AppError:
    return ValidationFailedError(
        [
            FieldError(
                field=error.field, code=error.rule.value, message=_UPLOAD_RULE_MESSAGES[error.rule]
            )
        ]
    )


_TRANSLATIONS: Final[Mapping[type[Exception], Callable[[Any], AppError]]] = {
    UploadRejectedError: _upload_rejected,
    AssetNotFoundError: lambda _: NotFoundError(
        "The asset does not exist.", code="asset_not_found"
    ),
    UploadMissingError: lambda _: ConflictError(
        "The file has not arrived in the storage.", code="upload_missing"
    ),
    UploadSizeMismatchError: lambda _: ConflictError(
        "The stored file does not have the announced size.", code="upload_size_mismatch"
    ),
    InvalidAssetStateError: lambda _: ConflictError(
        "The asset's state does not allow this.", code="invalid_asset_state"
    ),
    AssetInUseError: lambda _: ConflictError(
        "The asset is still used, e.g. in a product gallery.", code="asset_in_use"
    ),
}


def install_error_translations(app: FastAPI) -> None:
    """Answer the media domain errors with their problem responses."""
    for error_type, translate in _TRANSLATIONS.items():
        add_error_translation(app, error_type, translate)
