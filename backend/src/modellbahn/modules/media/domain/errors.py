"""Errors of the media domain. The API layer decides how they are presented."""

from enum import StrEnum


class MediaError(Exception):
    """Base of every error raised by the media module."""


class UploadRule(StrEnum):
    """The upload rule an announced file broke."""

    UNSUPPORTED_KIND = "unsupported_kind"
    UNSUPPORTED_TYPE = "unsupported_type"
    EMPTY = "empty"
    TOO_LARGE = "too_large"
    INVALID_CHECKSUM = "invalid_checksum"
    INVALID_FILENAME = "invalid_filename"


class UploadRejectedError(MediaError):
    """The announced file cannot be accepted (type, size, checksum or name)."""

    def __init__(self, rule: UploadRule, field: str) -> None:
        super().__init__(f"upload rejected: {rule}")
        self.rule = rule
        self.field = field


class AssetNotFoundError(MediaError):
    """No asset with this id."""


class UploadMissingError(MediaError):
    """The upload was to be completed, but the storage has no such object (yet)."""


class UploadSizeMismatchError(MediaError):
    """The stored object does not have the size announced in the upload ticket."""


class InvalidAssetStateError(MediaError):
    """The asset is not in a state that allows this action (e.g. reprocessing a pending one)."""


class AssetInUseError(MediaError):
    """Something still refers to the asset (e.g. a product gallery), so it cannot be deleted."""


class FailureCode(StrEnum):
    """Why processing an asset failed, as shown in the admin area."""

    UNSUPPORTED_FORMAT = "unsupported_format"
    TOO_MANY_PIXELS = "too_many_pixels"
    TOO_SMALL = "too_small"
    UNREADABLE = "unreadable"
    PROCESSING_ERROR = "processing_error"


class ImageRejectedError(MediaError):
    """The uploaded file is no usable image. Permanent: another attempt fails the same way."""

    def __init__(self, code: FailureCode, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail
