"""Media use cases and the worker's processing, against the database and a fake storage."""

from datetime import timedelta
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine

from modellbahn.modules.media.application.handlers import MediaProcessingHandlers
from modellbahn.modules.media.application.services import MediaService
from modellbahn.modules.media.domain.errors import (
    AssetInUseError,
    AssetNotFoundError,
    FailureCode,
    InvalidAssetStateError,
    UploadMissingError,
    UploadRejectedError,
    UploadSizeMismatchError,
)
from modellbahn.modules.media.domain.events import AssetDeleted, AssetUploaded
from modellbahn.modules.media.domain.model import (
    MAX_PROCESSING_ATTEMPTS,
    STALE_UPLOAD_AGE,
    UPLOAD_URL_LIFETIME,
    AssetStatus,
)
from modellbahn.platform.clock import FixedClock
from modellbahn.platform.outbox import outbox_table
from tests.conftest import Deliver
from tests.media_support import (
    InMemoryMediaStorage,
    photo,
    ready_image,
    sha256,
    uploaded_image,
)


async def outbox(engine: AsyncEngine) -> list[Any]:
    async with engine.connect() as connection:
        rows = await connection.execute(
            select(
                outbox_table.c.event_type, outbox_table.c.status, outbox_table.c.payload
            ).order_by(outbox_table.c.id)
        )
        return list(rows)


async def announce(media: MediaService, data: bytes, **changes: Any) -> Any:
    values: dict[str, Any] = {
        "filename": "Stellwerk.jpg",
        "mime_type": "image/jpeg",
        "size_bytes": len(data),
        "sha256": sha256(data),
        "uploaded_by": None,
    }
    values.update(changes)
    return await media.request_upload(**values)


class TestUploadTicket:
    async def test_a_new_file_gets_a_signed_url(
        self, media: MediaService, media_storage: InMemoryMediaStorage, clock: FixedClock
    ) -> None:
        data = photo()
        ticket = await announce(media, data)
        assert ticket.asset.status is AssetStatus.PENDING_UPLOAD
        assert ticket.upload is not None
        assert ticket.upload.method == "PUT"
        assert ticket.upload.headers == {"Content-Type": "image/jpeg"}
        assert ticket.upload.expires_at == clock.now() + UPLOAD_URL_LIFETIME
        assert media_storage.presigned[-1] == {
            "key": ticket.asset.original_key,
            "content_type": "image/jpeg",
            "content_length": len(data),
            "expires_in": UPLOAD_URL_LIFETIME,
        }

    async def test_the_same_file_twice_is_the_same_asset(
        self, media: MediaService, media_storage: InMemoryMediaStorage
    ) -> None:
        data = photo()
        first = await announce(media, data)
        # Not uploaded yet: a fresh URL, now for the type the browser reports this time.
        again = await announce(media, data, filename="kopie.heic", mime_type="image/heic")
        assert again.asset.id == first.asset.id
        assert again.upload is not None
        assert again.asset.original_filename == "kopie.heic"
        assert media_storage.presigned[-1]["content_type"] == "image/heic"
        media_storage.upload(first.asset.id, data)
        await media.complete_upload(first.asset.id)
        known = await announce(media, data)
        assert known.asset.id == first.asset.id
        assert known.upload is None

    async def test_rules_are_checked_before_anything_is_stored(
        self, media: MediaService, engine: AsyncEngine
    ) -> None:
        with pytest.raises(UploadRejectedError):
            await announce(media, b"x", mime_type="image/gif")
        async with engine.connect() as connection:
            assert await connection.scalar(text("SELECT count(*) FROM media.assets")) == 0


class TestCompleteUpload:
    async def test_needs_the_file_in_the_storage(
        self, media: MediaService, media_storage: InMemoryMediaStorage
    ) -> None:
        data = photo()
        ticket = await announce(media, data)
        with pytest.raises(UploadMissingError):
            await media.complete_upload(ticket.asset.id)
        media_storage.upload(ticket.asset.id, data[:-1])
        with pytest.raises(UploadSizeMismatchError):
            await media.complete_upload(ticket.asset.id)
        with pytest.raises(AssetNotFoundError):
            await media.complete_upload(UUID(int=1))

    async def test_completes_once_and_hands_over_to_the_worker(
        self, media: MediaService, media_storage: InMemoryMediaStorage, engine: AsyncEngine
    ) -> None:
        asset = await uploaded_image(media, media_storage)
        again = await media.complete_upload(asset.id)
        assert asset.status is again.status is AssetStatus.UPLOADED
        assert [row.event_type for row in await outbox(engine)] == [AssetUploaded.event_type]


class TestProcessing:
    async def test_the_worker_renders_and_publishes_every_size(
        self,
        media: MediaService,
        media_storage: InMemoryMediaStorage,
        deliver: Deliver,
        engine: AsyncEngine,
    ) -> None:
        asset = await ready_image(media, media_storage, deliver, photo(1300, 900))
        assert asset.image is not None
        assert (asset.image.width, asset.image.height) == (1300, 900)
        assert asset.image.lqip.startswith("data:image/webp;base64,")
        assert {(r.name, r.format.value) for r in asset.renditions} == {
            (name, fmt) for name in ("thumb", "sm", "md", "og") for fmt in ("webp", "avif")
        }
        for rendition in asset.renditions:
            stored = media_storage.public[rendition.storage_key]
            assert rendition.storage_key.startswith(f"{asset.id}/{rendition.name}-")
            assert stored.content_type == rendition.format.mime_type
            assert rendition.size_bytes == len(stored.data)
        # The handler wrote the ready event; the next batch forwards it to the admin area.
        await deliver()
        assert [(r.event_type, r.status) for r in await outbox(engine)] == [
            ("media.asset.uploaded", "published"),
            ("media.asset.ready", "published"),
        ]

    async def test_a_repeated_delivery_changes_nothing(
        self,
        media: MediaService,
        media_storage: InMemoryMediaStorage,
        media_handlers: MediaProcessingHandlers,
        deliver: Deliver,
        clock: FixedClock,
    ) -> None:
        asset = await ready_image(media, media_storage, deliver)
        keys = sorted(media_storage.public)
        await media_handlers.process_upload(
            AssetUploaded(aggregate_id=asset.id, occurred_at=clock.now())
        )
        assert sorted(media_storage.public) == keys
        assert (await media.get(asset.id)).ready_at == asset.ready_at

    async def test_an_unusable_file_fails_at_once(
        self,
        media: MediaService,
        media_storage: InMemoryMediaStorage,
        deliver: Deliver,
        engine: AsyncEngine,
    ) -> None:
        # A photo whose upload broke off: the bytes start like a JPEG and then end.
        asset = await uploaded_image(media, media_storage, photo()[:2000])
        await deliver()
        failed = await media.get(asset.id)
        assert failed.status is AssetStatus.FAILED
        assert failed.failure_code is FailureCode.UNREADABLE
        assert failed.attempts == 1
        rows = await outbox(engine)
        assert rows[-1].event_type == "media.asset.failed"
        assert rows[-1].payload == {"failure_code": "unreadable"}

    async def test_transient_errors_are_retried_and_finally_fail(
        self,
        media: MediaService,
        media_storage: InMemoryMediaStorage,
        media_handlers: MediaProcessingHandlers,
        clock: FixedClock,
    ) -> None:
        asset = await uploaded_image(media, media_storage)
        event = AssetUploaded(aggregate_id=asset.id, occurred_at=clock.now())
        media_storage.fail_reads = MAX_PROCESSING_ATTEMPTS
        for attempt in range(1, MAX_PROCESSING_ATTEMPTS):
            # Re-raised, so the outbox schedules another attempt.
            with pytest.raises(ConnectionError):
                await media_handlers.process_upload(event)
            current = await media.get(asset.id)
            assert (current.status, current.attempts) == (AssetStatus.UPLOADED, attempt)
        await media_handlers.process_upload(event)
        failed = await media.get(asset.id)
        assert failed.status is AssetStatus.FAILED
        assert failed.failure_code is FailureCode.PROCESSING_ERROR
        assert failed.last_error == "ConnectionError: storage unreachable"

    async def test_reprocessing_replaces_the_sizes(
        self,
        media: MediaService,
        media_storage: InMemoryMediaStorage,
        deliver: Deliver,
    ) -> None:
        asset = await ready_image(media, media_storage, deliver)
        old_keys = {r.storage_key for r in asset.renditions}
        # A changed original stands in for a changed size catalogue.
        media_storage.upload(asset.id, photo(700, 500, colour=(20, 120, 200)))
        assert (await media.reprocess(asset.id)).status is AssetStatus.UPLOADED
        await deliver()
        again = await media.get(asset.id)
        new_keys = {r.storage_key for r in again.renditions}
        assert again.is_ready
        assert new_keys.isdisjoint(old_keys)
        assert set(media_storage.public) == new_keys
        with pytest.raises(InvalidAssetStateError):
            await media.reprocess((await uploaded_image(media, media_storage, photo(300, 300))).id)


class TestDeletion:
    async def test_deleting_removes_the_files(
        self, media: MediaService, media_storage: InMemoryMediaStorage, deliver: Deliver
    ) -> None:
        asset = await ready_image(media, media_storage, deliver)
        await media.delete(asset.id)
        with pytest.raises(AssetNotFoundError):
            await media.get(asset.id)
        await deliver()
        assert media_storage.private == {}
        assert media_storage.public == {}

    async def test_an_image_in_a_gallery_cannot_be_deleted(
        self, media: MediaService, media_storage: InMemoryMediaStorage, engine: AsyncEngine
    ) -> None:
        asset = await uploaded_image(media, media_storage)
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "INSERT INTO catalog.products (id, number, slug, name, status, created_at, "
                    "updated_at) VALUES (gen_random_uuid(), 1, 'p', 'P', 'draft', now(), now()) "
                    "RETURNING id"
                )
            )
            await connection.execute(
                text(
                    "INSERT INTO catalog.product_media (product_id, asset_id, position, role) "
                    "SELECT id, :asset, 0, 'gallery' FROM catalog.products"
                ),
                {"asset": asset.id},
            )
        with pytest.raises(AssetInUseError):
            await media.delete(asset.id)
        assert (await media.get(asset.id)).status is AssetStatus.UPLOADED

    async def test_stale_tickets_are_purged(
        self,
        media: MediaService,
        media_storage: InMemoryMediaStorage,
        clock: FixedClock,
        engine: AsyncEngine,
    ) -> None:
        stale = await announce(media, photo(400, 400))
        kept = await uploaded_image(media, media_storage)
        clock.advance(STALE_UPLOAD_AGE - timedelta(minutes=1))
        assert await media.purge_stale_uploads() == 0
        clock.advance(timedelta(minutes=2))
        assert await media.purge_stale_uploads() == 1
        with pytest.raises(AssetNotFoundError):
            await media.get(stale.asset.id)
        assert (await media.get(kept.id)).status is AssetStatus.UPLOADED
        rows = await outbox(engine)
        assert rows[-1].event_type == AssetDeleted.event_type


async def test_the_database_only_puts_images_into_galleries(
    media: MediaService, media_storage: InMemoryMediaStorage, engine: AsyncEngine
) -> None:
    asset = await uploaded_image(media, media_storage)
    async with engine.begin() as connection:
        await connection.execute(
            text("UPDATE media.assets SET kind = 'model_3d' WHERE id = :id"), {"id": asset.id}
        )
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "INSERT INTO catalog.products (id, number, slug, name, status, created_at, "
                "updated_at) VALUES (gen_random_uuid(), 2, 'q', 'Q', 'draft', now(), now())"
            )
        )
    insert_into_gallery = text(
        "INSERT INTO catalog.product_media (product_id, asset_id, position, role) "
        "SELECT id, :asset, 0, 'gallery' FROM catalog.products"
    )
    async with engine.connect() as connection:
        with pytest.raises(IntegrityError, match="fk_product_media_asset_id_asset_kind_assets"):
            await connection.execute(insert_into_gallery, {"asset": asset.id})
