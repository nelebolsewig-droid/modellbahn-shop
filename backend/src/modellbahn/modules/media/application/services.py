"""Media use cases of the admin area: upload tickets, completion, reprocessing, deletion.

Every public method runs in its own unit of work. Files never pass through the API:
the browser uploads straight into the private storage with a signed URL, and the
worker reads them from there.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Final
from uuid import UUID

import structlog

from modellbahn.modules.media.application.ports import MediaStorage, MediaUnitOfWork
from modellbahn.modules.media.domain.errors import (
    AssetInUseError,
    AssetNotFoundError,
    UploadMissingError,
)
from modellbahn.modules.media.domain.model import (
    STALE_UPLOAD_AGE,
    UPLOAD_URL_LIFETIME,
    Asset,
    AssetKind,
    check_image_upload,
    normalize_filename,
)
from modellbahn.platform.clock import Clock
from modellbahn.platform.uow import ForeignKeyViolationError, UniqueViolationError

type UnitOfWorkFactory = Callable[[], MediaUnitOfWork]

STALE_UPLOAD_BATCH: Final = 100

_logger = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class UploadTarget:
    """Where and how the browser sends the file. Only these headers are allowed."""

    url: str
    method: str
    headers: dict[str, str]
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class UploadTicket:
    """The asset for an announced file; ``upload`` is ``None`` if the file is known already."""

    asset: Asset
    upload: UploadTarget | None


class MediaService:
    """The media module's use cases, independent of HTTP."""

    def __init__(
        self, *, uow_factory: UnitOfWorkFactory, storage: MediaStorage, clock: Clock
    ) -> None:
        self._uow = uow_factory
        self._storage = storage
        self._clock = clock

    async def request_upload(
        self,
        *,
        filename: str,
        mime_type: str,
        size_bytes: int,
        sha256: str,
        uploaded_by: UUID | None,
    ) -> UploadTicket:
        """Announce an image upload and get a signed URL for it.

        The browser computes the SHA-256 before uploading, so a file that is already
        stored is recognised before a single byte travels: the answer then carries the
        existing asset and no URL. A ticket that was never used gets a fresh URL.
        """
        checksum = check_image_upload(mime_type=mime_type, size_bytes=size_bytes, sha256=sha256)
        filename = normalize_filename(filename)
        try:
            asset = await self._find_or_announce(
                filename, mime_type, size_bytes, checksum, uploaded_by
            )
        except UniqueViolationError:
            # A concurrent request announced the same file first; use that asset.
            asset = await self._find_or_announce(
                filename, mime_type, size_bytes, checksum, uploaded_by
            )
        if not asset.awaits_upload:
            return UploadTicket(asset=asset, upload=None)
        url = self._storage.presign_original_upload(
            asset.original_key,
            content_type=asset.mime_type,
            content_length=asset.size_bytes,
            expires_in=UPLOAD_URL_LIFETIME,
        )
        target = UploadTarget(
            url=url,
            method="PUT",
            headers={"Content-Type": asset.mime_type},
            expires_at=self._clock.now() + UPLOAD_URL_LIFETIME,
        )
        return UploadTicket(asset=asset, upload=target)

    async def _find_or_announce(
        self,
        filename: str,
        mime_type: str,
        size_bytes: int,
        sha256: str,
        uploaded_by: UUID | None,
    ) -> Asset:
        now = self._clock.now()
        async with self._uow() as uow:
            existing = await uow.assets.get_by_checksum(AssetKind.IMAGE, sha256)
            if existing is not None and not existing.awaits_upload:
                return existing
            if existing is not None:
                existing.reannounce(filename=filename, mime_type=mime_type, now=now)
                asset = existing
            else:
                asset = Asset.announce(
                    kind=AssetKind.IMAGE,
                    filename=filename,
                    mime_type=mime_type,
                    size_bytes=size_bytes,
                    sha256=sha256,
                    uploaded_by=uploaded_by,
                    now=now,
                )
                uow.assets.add(asset)
            await uow.commit()
            return asset

    async def complete_upload(self, asset_id: UUID) -> Asset:
        """Check that the file arrived complete and hand it to the worker. Idempotent."""
        async with self._uow() as uow:
            asset = await self._require(uow, asset_id, for_update=True)
            if not asset.awaits_upload:
                return asset
            stored_size = await self._storage.original_size(asset.original_key)
            if stored_size is None:
                raise UploadMissingError
            event = asset.complete_upload(stored_size, self._clock.now())
            if event is not None:
                uow.publish(event)
            await uow.commit()
            return asset

    async def get(self, asset_id: UUID) -> Asset:
        async with self._uow() as uow:
            return await self._require(uow, asset_id)

    async def reprocess(self, asset_id: UUID) -> Asset:
        """Render the sizes again (after a failure, or for a changed size catalogue)."""
        async with self._uow() as uow:
            asset = await self._require(uow, asset_id, for_update=True)
            uow.publish(asset.reprocess(self._clock.now()))
            await uow.commit()
            return asset

    async def delete(self, asset_id: UUID) -> None:
        """Delete an asset nothing refers to; the worker then removes its files."""
        async with self._uow() as uow:
            asset = await self._require(uow, asset_id, for_update=True)
            await uow.assets.delete(asset)
            uow.publish(asset.delete(self._clock.now()))
            try:
                await uow.commit()
            except ForeignKeyViolationError as exc:
                raise AssetInUseError from exc

    async def purge_stale_uploads(self) -> int:
        """Remove tickets whose file has not arrived within a day; returns how many.

        Runs hourly in the worker. Such assets cannot be in use: galleries only take
        assets whose upload was completed.
        """
        now = self._clock.now()
        async with self._uow() as uow:
            stale = await uow.assets.stale_uploads(
                created_before=now - STALE_UPLOAD_AGE, limit=STALE_UPLOAD_BATCH
            )
            for asset in stale:
                await uow.assets.delete(asset)
                # A partial upload may have left an object behind.
                uow.publish(asset.delete(now))
            await uow.commit()
        if stale:
            _logger.info("media.stale_uploads_removed", count=len(stale))
        return len(stale)

    @staticmethod
    async def _require(uow: MediaUnitOfWork, asset_id: UUID, *, for_update: bool = False) -> Asset:
        asset = await uow.assets.get(asset_id, for_update=for_update)
        if asset is None:
            raise AssetNotFoundError
        return asset
