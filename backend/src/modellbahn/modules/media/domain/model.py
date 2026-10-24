"""The media model: an uploaded file (asset), the facts of an image and its rendered sizes.

Plain dataclasses without any framework, mapped imperatively by the infrastructure.
An asset goes ``pending_upload`` → ``uploaded`` → ``ready`` (or ``failed``). The
original stays in the private storage under :attr:`Asset.original_key`; the rendered
sizes are public and immutable. Every method that depends on time takes ``now``.
"""

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Final
from uuid import UUID

from modellbahn.modules.media.domain.errors import (
    FailureCode,
    InvalidAssetStateError,
    UploadRejectedError,
    UploadRule,
    UploadSizeMismatchError,
)
from modellbahn.modules.media.domain.events import (
    AssetDeleted,
    AssetFailed,
    AssetReady,
    AssetUploaded,
)
from modellbahn.modules.media.domain.renditions import RenditionFormat
from modellbahn.platform.ids import new_id

# What a browser may announce for a product photo. The worker checks the actual bytes
# (magic numbers) again, the announced type only decides what the upload URL allows.
ACCEPTED_IMAGE_TYPES: Final = frozenset(
    {"image/jpeg", "image/png", "image/webp", "image/avif", "image/heic", "image/heif"}
)
IMAGE_MAX_BYTES: Final = 50 * 1024 * 1024
# Against decompression bombs: a small file can decode to gigabytes of pixels.
IMAGE_MAX_PIXELS: Final = 100_000_000
FILENAME_MAX_LENGTH: Final = 255
MAX_PROCESSING_ATTEMPTS: Final = 3
UPLOAD_URL_LIFETIME: Final = timedelta(minutes=15)
# Tickets whose file never arrived are removed after this long.
STALE_UPLOAD_AGE: Final = timedelta(hours=24)
LAST_ERROR_MAX_LENGTH: Final = 1000

_SHA256: Final = re.compile(r"[0-9a-f]{64}")
_BIDI_CONTROLS: Final = frozenset("\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069")


class AssetKind(StrEnum):
    IMAGE = "image"
    # Reserved for the print files of step 6; uploads of this kind are refused for now.
    MODEL_3D = "model_3d"


class AssetStatus(StrEnum):
    PENDING_UPLOAD = "pending_upload"
    UPLOADED = "uploaded"
    READY = "ready"
    FAILED = "failed"


def normalize_filename(value: str) -> str:
    """The file name as shown in the admin area: no path, no control characters.

    Browsers send only the name, but some (and every script) can send a path; only the
    last part counts. Raises :class:`UploadRejectedError` if nothing usable is left.
    """
    name = re.split(r"[\\/]", value)[-1]
    name = unicodedata.normalize("NFC", name)
    name = "".join(
        char for char in name if unicodedata.category(char) != "Cc" and char not in _BIDI_CONTROLS
    )
    name = " ".join(name.split())
    if not name or name in {".", ".."} or len(name) > FILENAME_MAX_LENGTH:
        raise UploadRejectedError(UploadRule.INVALID_FILENAME, "filename")
    return name


def check_image_upload(*, mime_type: str, size_bytes: int, sha256: str) -> str:
    """Validate an announced image upload; returns the checksum in lower case."""
    if mime_type not in ACCEPTED_IMAGE_TYPES:
        raise UploadRejectedError(UploadRule.UNSUPPORTED_TYPE, "mime_type")
    if size_bytes <= 0:
        raise UploadRejectedError(UploadRule.EMPTY, "size_bytes")
    if size_bytes > IMAGE_MAX_BYTES:
        raise UploadRejectedError(UploadRule.TOO_LARGE, "size_bytes")
    checksum = sha256.lower()
    if not _SHA256.fullmatch(checksum):
        raise UploadRejectedError(UploadRule.INVALID_CHECKSUM, "sha256")
    return checksum


def original_key(asset_id: UUID) -> str:
    """Key of the original in the private storage."""
    return f"incoming/{asset_id}/original"


@dataclass(eq=False, kw_only=True)
class ImageDetails:
    """What the worker learned about an image: size, colour, placeholder, fingerprint."""

    asset_id: UUID
    width: int
    height: int
    # "#rrggbb", shown behind the image while it loads.
    dominant_color: str
    # A tiny blurred version as data URI, faded out once the real image has loaded.
    lqip: str
    # 64-bit difference hash (signed, to fit a bigint) for finding near-duplicates.
    phash: int


@dataclass(eq=False, kw_only=True)
class Rendition:
    """One rendered size in one format, stored publicly under ``storage_key``."""

    asset_id: UUID
    name: str
    format: RenditionFormat
    width: int
    height: int
    storage_key: str
    size_bytes: int


@dataclass(eq=False, kw_only=True)
class Asset:
    """An uploaded file. The aggregate root of the media module.

    ``(kind, sha256)`` is unique: the same file uploaded twice is the same asset.
    Other modules refer to ``(id, kind)``, so a gallery can only hold images.
    """

    id: UUID
    kind: AssetKind
    status: AssetStatus
    original_key: str
    original_filename: str
    mime_type: str
    size_bytes: int
    sha256: str
    attempts: int
    failure_code: FailureCode | None
    last_error: str | None
    uploaded_by: UUID | None
    created_at: datetime
    updated_at: datetime
    ready_at: datetime | None
    image: ImageDetails | None = None
    renditions: list[Rendition] = field(default_factory=list)
    # Maintained by the persistence layer for optimistic locking.
    version: int = 1

    @classmethod
    def announce(
        cls,
        *,
        kind: AssetKind,
        filename: str,
        mime_type: str,
        size_bytes: int,
        sha256: str,
        uploaded_by: UUID | None,
        now: datetime,
    ) -> "Asset":
        """A new asset waiting for its upload. Only images are accepted so far."""
        if kind is not AssetKind.IMAGE:
            raise UploadRejectedError(UploadRule.UNSUPPORTED_KIND, "kind")
        checksum = check_image_upload(mime_type=mime_type, size_bytes=size_bytes, sha256=sha256)
        asset_id = new_id()
        return cls(
            id=asset_id,
            kind=kind,
            status=AssetStatus.PENDING_UPLOAD,
            original_key=original_key(asset_id),
            original_filename=normalize_filename(filename),
            mime_type=mime_type,
            size_bytes=size_bytes,
            sha256=checksum,
            attempts=0,
            failure_code=None,
            last_error=None,
            uploaded_by=uploaded_by,
            created_at=now,
            updated_at=now,
            ready_at=None,
        )

    @property
    def awaits_upload(self) -> bool:
        return self.status is AssetStatus.PENDING_UPLOAD

    @property
    def is_ready(self) -> bool:
        return self.status is AssetStatus.READY

    def is_stale_upload(self, now: datetime) -> bool:
        """True for a ticket whose file has not arrived within :data:`STALE_UPLOAD_AGE`."""
        return self.awaits_upload and now - self.created_at >= STALE_UPLOAD_AGE

    def reannounce(self, *, filename: str, mime_type: str, now: datetime) -> None:
        """The same file announced again before its upload: the new URL must match it."""
        if not self.awaits_upload:
            raise InvalidAssetStateError(f"asset {self.id} is {self.status}")
        check_image_upload(mime_type=mime_type, size_bytes=self.size_bytes, sha256=self.sha256)
        self.original_filename = normalize_filename(filename)
        self.mime_type = mime_type
        self.updated_at = now

    def complete_upload(self, stored_size: int, now: datetime) -> AssetUploaded | None:
        """The original is in the storage: hand it to the worker.

        Completing twice is harmless and returns no second event. A stored object of
        another size than announced is refused; the browser may upload it again.
        """
        if not self.awaits_upload:
            return None
        if stored_size != self.size_bytes:
            raise UploadSizeMismatchError
        self.status = AssetStatus.UPLOADED
        self.updated_at = now
        return AssetUploaded(aggregate_id=self.id, occurred_at=now)

    def mark_ready(
        self, *, image: ImageDetails, renditions: list[Rendition], now: datetime
    ) -> AssetReady:
        """Store the result of processing; the sizes are already in the public storage."""
        if self.status is not AssetStatus.UPLOADED:
            raise InvalidAssetStateError(f"asset {self.id} is {self.status}, not uploaded")
        self.image = image
        self.renditions = renditions
        self.status = AssetStatus.READY
        self.failure_code = None
        self.last_error = None
        self.ready_at = now
        self.updated_at = now
        return AssetReady(aggregate_id=self.id, occurred_at=now)

    def record_failure(
        self, *, code: FailureCode, error: str, permanent: bool, now: datetime
    ) -> AssetFailed | None:
        """Count a failed processing attempt.

        A permanent failure (the file is no usable image) ends processing at once;
        otherwise the asset fails after :data:`MAX_PROCESSING_ATTEMPTS`. Returns the
        event only when the asset has failed for good, until then the worker retries.
        """
        if self.status is not AssetStatus.UPLOADED:
            raise InvalidAssetStateError(f"asset {self.id} is {self.status}, not uploaded")
        self.attempts += 1
        self.failure_code = code
        self.last_error = error[:LAST_ERROR_MAX_LENGTH]
        self.updated_at = now
        if not permanent and self.attempts < MAX_PROCESSING_ATTEMPTS:
            return None
        self.status = AssetStatus.FAILED
        return AssetFailed(aggregate_id=self.id, occurred_at=now, failure_code=code)

    def reprocess(self, now: datetime) -> AssetUploaded:
        """Render the sizes again, e.g. after a failure or a change of the size catalogue."""
        if self.status not in {AssetStatus.FAILED, AssetStatus.READY}:
            raise InvalidAssetStateError(f"asset {self.id} is {self.status}")
        self.status = AssetStatus.UPLOADED
        self.attempts = 0
        self.failure_code = None
        self.last_error = None
        self.updated_at = now
        return AssetUploaded(aggregate_id=self.id, occurred_at=now)

    def delete(self, now: datetime) -> AssetDeleted:
        """The event that removes the files; the repository removes the row."""
        return AssetDeleted(aggregate_id=self.id, occurred_at=now)
