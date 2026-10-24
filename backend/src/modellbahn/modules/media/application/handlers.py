"""Outbox event handlers of the media module: render uploaded images, remove deleted files.

Delivery is at least once, so both handlers are idempotent. Processing reads the
asset, works without holding a transaction (decoding and encoding take seconds),
publishes the sizes under content-addressed keys and only then records the result.
A repeated delivery finds the asset ``ready`` and does nothing; a delivery that died
halfway left public files nobody refers to yet, which the next run overwrites with
the same keys.
"""

import asyncio
import hashlib
from uuid import UUID

import structlog

from modellbahn.modules.media.application.ports import (
    ImageProcessor,
    MediaStorage,
    ProcessedImage,
)
from modellbahn.modules.media.application.services import UnitOfWorkFactory
from modellbahn.modules.media.domain.errors import FailureCode, ImageRejectedError
from modellbahn.modules.media.domain.events import AssetDeleted, AssetUploaded
from modellbahn.modules.media.domain.model import (
    IMAGE_MAX_BYTES,
    AssetStatus,
    ImageDetails,
    Rendition,
)
from modellbahn.modules.media.domain.renditions import storage_key
from modellbahn.platform.clock import Clock
from modellbahn.platform.outbox import HandlerRegistry

_logger = structlog.get_logger(__name__)


class MediaProcessingHandlers:
    """The worker's part of the media pipeline (KONZEPT §6, steps 4 to 6)."""

    def __init__(
        self,
        *,
        uow_factory: UnitOfWorkFactory,
        storage: MediaStorage,
        processor: ImageProcessor,
        clock: Clock,
    ) -> None:
        self._uow = uow_factory
        self._storage = storage
        self._processor = processor
        self._clock = clock

    def register(self, registry: HandlerRegistry) -> None:
        """Subscribe the handlers to their events."""
        registry.register(AssetUploaded, self.process_upload)
        registry.register(AssetDeleted, self.remove_files)

    async def process_upload(self, event: AssetUploaded) -> None:
        """Render every size of an uploaded image and mark the asset ready.

        A file that is no usable image fails at once. Any other error (the storage is
        unreachable, say) is counted and re-raised, so the outbox retries with growing
        delays; the third failure marks the asset failed.
        """
        asset_id = event.aggregate_id
        async with self._uow() as uow:
            asset = await uow.assets.get(asset_id)
        if asset is None or asset.status is not AssetStatus.UPLOADED:
            return
        log = _logger.bind(asset_id=str(asset_id))
        try:
            original = await self._storage.read_original(
                asset.original_key, max_bytes=IMAGE_MAX_BYTES
            )
            processed = await asyncio.to_thread(self._processor.process, original)
            renditions = await self._publish(asset_id, processed)
        except ImageRejectedError as exc:
            log.info("media.image_rejected", failure_code=exc.code.value, detail=exc.detail)
            await self._record_failure(asset_id, exc.code, exc.detail, permanent=True)
            return
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            if await self._record_failure(
                asset_id, FailureCode.PROCESSING_ERROR, error, permanent=False
            ):
                log.error("media.processing_failed", error=error)
                return
            raise
        await self._finish(asset_id, processed, renditions)
        log.info("media.asset_ready", renditions=len(renditions))

    async def remove_files(self, event: AssetDeleted) -> None:
        """Delete the files of a deleted asset from both buckets."""
        await self._storage.delete_files(event.aggregate_id)

    async def _publish(self, asset_id: UUID, processed: ProcessedImage) -> list[Rendition]:
        renditions = [
            Rendition(
                asset_id=asset_id,
                name=encoded.name,
                format=encoded.format,
                width=encoded.width,
                height=encoded.height,
                storage_key=storage_key(
                    asset_id, encoded.name, hashlib.sha256(encoded.data).hexdigest(), encoded.format
                ),
                size_bytes=len(encoded.data),
            )
            for encoded in processed.renditions
        ]
        await asyncio.gather(
            *(
                self._storage.publish_rendition(
                    rendition.storage_key, encoded.data, content_type=encoded.format.mime_type
                )
                for rendition, encoded in zip(renditions, processed.renditions, strict=True)
            )
        )
        return renditions

    async def _finish(
        self, asset_id: UUID, processed: ProcessedImage, renditions: list[Rendition]
    ) -> None:
        async with self._uow() as uow:
            asset = await uow.assets.get(asset_id, for_update=True)
            if asset is None:
                # Deleted while it was being processed: take the new files away again.
                await self._storage.delete_files(asset_id)
                return
            if asset.status is not AssetStatus.UPLOADED:
                return
            previous = {rendition.storage_key for rendition in asset.renditions}
            details = ImageDetails(
                asset_id=asset_id,
                width=processed.width,
                height=processed.height,
                dominant_color=processed.dominant_color,
                lqip=processed.lqip,
                phash=processed.phash,
            )
            uow.publish(
                asset.mark_ready(image=details, renditions=renditions, now=self._clock.now())
            )
            await uow.commit()
        # A reprocessed image has new keys; the old files are referred to by nothing now.
        outdated = previous - {rendition.storage_key for rendition in renditions}
        if outdated:
            await self._storage.delete_renditions(sorted(outdated))

    async def _record_failure(
        self, asset_id: UUID, code: FailureCode, error: str, *, permanent: bool
    ) -> bool:
        """Count the failed attempt; True if processing is over for this asset."""
        async with self._uow() as uow:
            asset = await uow.assets.get(asset_id, for_update=True)
            if asset is None or asset.status is not AssetStatus.UPLOADED:
                return True
            event = asset.record_failure(
                code=code, error=error, permanent=permanent, now=self._clock.now()
            )
            if event is not None:
                uow.publish(event)
            await uow.commit()
            return event is not None
