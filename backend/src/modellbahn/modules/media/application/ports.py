"""What the media use cases need from the outside world, as protocols.

The infrastructure layer implements them; tests may substitute their own.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from types import TracebackType
from typing import Protocol, Self
from uuid import UUID

from modellbahn.modules.media.domain.model import Asset, AssetKind
from modellbahn.modules.media.domain.renditions import RenditionFormat
from modellbahn.platform.events import DomainEvent


class AssetRepository(Protocol):
    async def get(self, asset_id: UUID, *, for_update: bool = False) -> Asset | None:
        """The asset with its image details and renditions. ``for_update`` locks the row."""
        ...

    async def get_by_checksum(self, kind: AssetKind, sha256: str) -> Asset | None: ...

    def add(self, asset: Asset) -> None: ...

    async def delete(self, asset: Asset) -> None: ...

    async def stale_uploads(self, *, created_before: datetime, limit: int) -> list[Asset]:
        """Assets still waiting for their upload, locked; rows locked elsewhere are skipped."""
        ...

    async def rendered_with_studio(self, *, enabled: bool, limit: int) -> list[Asset]:
        """Finished images whose studio switch is ``enabled``, oldest first, locked."""
        ...


class MediaUnitOfWork(Protocol):
    """One transaction over the media repositories (see ``platform.uow``)."""

    @property
    def assets(self) -> AssetRepository: ...

    async def __aenter__(self) -> Self: ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...

    def publish(self, *events: DomainEvent) -> None: ...

    async def flush(self) -> None: ...

    async def commit(self) -> None: ...


class MediaStorage(Protocol):
    """The object storage: originals stay private, rendered sizes are public.

    Every key of an asset starts with its id, so :meth:`delete_files` finds them all.
    """

    def presign_original_upload(
        self, key: str, *, content_type: str, content_length: int, expires_in: timedelta
    ) -> str:
        """A URL the browser can PUT exactly this file to (type and length are signed)."""
        ...

    async def original_size(self, key: str) -> int | None:
        """Size of the stored original, ``None`` if nothing was uploaded."""
        ...

    async def read_original(self, key: str, *, max_bytes: int) -> bytes:
        """The original's bytes; refuses objects larger than ``max_bytes``."""
        ...

    async def publish_rendition(self, key: str, data: bytes, *, content_type: str) -> None:
        """Store a rendered size publicly, cacheable for good (its key never changes)."""
        ...

    async def delete_renditions(self, keys: list[str]) -> None: ...

    async def delete_files(self, asset_id: UUID) -> None:
        """Remove the original and every rendered size of the asset. Idempotent."""
        ...


@dataclass(frozen=True, slots=True)
class EncodedRendition:
    name: str
    format: RenditionFormat
    width: int
    height: int
    data: bytes


@dataclass(frozen=True, slots=True)
class ProcessedImage:
    """Everything the worker derived from an original, ready to be stored."""

    width: int
    height: int
    dominant_color: str
    lqip: str
    phash: int
    renditions: list[EncodedRendition]
    # True when the photo studio finished the photo, False when it is shown as uploaded.
    studio_applied: bool = False


class ImageProcessor(Protocol):
    def process(self, data: bytes, *, studio: bool = False) -> ProcessedImage:
        """Decode, check and render an original. CPU-bound and blocking: run it in a thread.

        With ``studio`` the photo studio finishes the photo first (cut out, light evened
        out, placed on the stage); a photo it finds no model in is rendered as it is.

        Raises :class:`~modellbahn.modules.media.domain.errors.ImageRejectedError` for
        files that are no usable image.
        """
        ...


class StudioGate(Protocol):
    """Decides when the photo studio may take its next photo.

    The studio needs over a gigabyte for some seconds. On a small server it works one
    photo at a time, with a pause in between, and only while memory is free.
    """

    def wait(self) -> tuple[timedelta, str] | None:
        """How long to wait before the next photo and why, or ``None`` to start now."""
        ...

    def done(self) -> None:
        """A photo is finished (or gave up); the pause before the next one begins."""
        ...
