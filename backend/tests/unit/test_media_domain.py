"""The media model without a database: upload rules, the asset's life cycle, size planning."""

from datetime import timedelta
from uuid import uuid4

import pytest

from modellbahn.modules.media.domain.errors import (
    FailureCode,
    InvalidAssetStateError,
    UploadRejectedError,
    UploadRule,
    UploadSizeMismatchError,
)
from modellbahn.modules.media.domain.events import AssetFailed, AssetReady, AssetUploaded
from modellbahn.modules.media.domain.model import (
    IMAGE_MAX_BYTES,
    MAX_PROCESSING_ATTEMPTS,
    STALE_UPLOAD_AGE,
    Asset,
    AssetKind,
    AssetStatus,
    ImageDetails,
    normalize_filename,
)
from modellbahn.modules.media.domain.renditions import (
    PlannedRendition,
    RenditionFormat,
    plan_renditions,
    storage_key,
)
from modellbahn.platform.events import event_registry
from tests.support import NOW

CHECKSUM = "ab" * 32


def announced(**changes: object) -> Asset:
    values: dict[str, object] = {
        "kind": AssetKind.IMAGE,
        "filename": "stellwerk.jpg",
        "mime_type": "image/jpeg",
        "size_bytes": 1234,
        "sha256": CHECKSUM,
        "uploaded_by": None,
        "now": NOW,
    }
    values.update(changes)
    return Asset.announce(**values)  # type: ignore[arg-type]


def details(asset: Asset) -> ImageDetails:
    return ImageDetails(
        asset_id=asset.id, width=640, height=480, dominant_color="#aa3322", lqip="data:", phash=1
    )


class TestUploadRules:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("Stellwerk.JPG", "Stellwerk.JPG"),
            ("C:\\fakepath\\foto 1.heic", "foto 1.heic"),
            ("../../etc/passwd", "passwd"),
            ("  Dach\t links .png ", "Dach links .png"),
            ("Bahnhof\u202e.jpg", "Bahnhof.jpg"),
        ],
    )
    def test_filenames_lose_paths_and_control_characters(self, raw: str, expected: str) -> None:
        assert normalize_filename(raw) == expected

    @pytest.mark.parametrize("raw", ["", "   ", "dir/", "..", "x" * 256])
    def test_unusable_filenames_are_refused(self, raw: str) -> None:
        with pytest.raises(UploadRejectedError) as caught:
            normalize_filename(raw)
        assert caught.value.rule is UploadRule.INVALID_FILENAME

    @pytest.mark.parametrize(
        ("changes", "rule", "field"),
        [
            ({"mime_type": "image/gif"}, UploadRule.UNSUPPORTED_TYPE, "mime_type"),
            ({"mime_type": "application/pdf"}, UploadRule.UNSUPPORTED_TYPE, "mime_type"),
            ({"size_bytes": 0}, UploadRule.EMPTY, "size_bytes"),
            ({"size_bytes": IMAGE_MAX_BYTES + 1}, UploadRule.TOO_LARGE, "size_bytes"),
            ({"sha256": "xyz"}, UploadRule.INVALID_CHECKSUM, "sha256"),
            ({"kind": AssetKind.MODEL_3D}, UploadRule.UNSUPPORTED_KIND, "kind"),
        ],
    )
    def test_announcements_breaking_a_rule_are_refused(
        self, changes: dict[str, object], rule: UploadRule, field: str
    ) -> None:
        with pytest.raises(UploadRejectedError) as caught:
            announced(**changes)
        assert (caught.value.rule, caught.value.field) == (rule, field)

    def test_announcement_creates_a_pending_asset(self) -> None:
        asset = announced(sha256=CHECKSUM.upper(), size_bytes=IMAGE_MAX_BYTES)
        assert asset.status is AssetStatus.PENDING_UPLOAD
        assert asset.sha256 == CHECKSUM
        assert asset.original_key == f"incoming/{asset.id}/original"
        assert asset.attempts == 0


class TestLifeCycle:
    def test_complete_upload_hands_the_asset_to_the_worker_once(self) -> None:
        asset = announced()
        event = asset.complete_upload(1234, NOW)
        assert isinstance(event, AssetUploaded)
        assert asset.status is AssetStatus.UPLOADED
        assert asset.complete_upload(1234, NOW) is None

    def test_complete_upload_refuses_another_size(self) -> None:
        asset = announced()
        with pytest.raises(UploadSizeMismatchError):
            asset.complete_upload(1233, NOW)
        assert asset.awaits_upload

    def test_reannounce_takes_the_new_name_and_type(self) -> None:
        asset = announced()
        asset.reannounce(filename="neu.heic", mime_type="image/heic", now=NOW)
        assert (asset.original_filename, asset.mime_type) == ("neu.heic", "image/heic")
        asset.complete_upload(1234, NOW)
        with pytest.raises(InvalidAssetStateError):
            asset.reannounce(filename="x.jpg", mime_type="image/jpeg", now=NOW)

    def test_mark_ready_needs_an_upload(self) -> None:
        asset = announced()
        with pytest.raises(InvalidAssetStateError):
            asset.mark_ready(image=details(asset), renditions=[], now=NOW)
        asset.complete_upload(1234, NOW)
        event = asset.mark_ready(image=details(asset), renditions=[], now=NOW)
        assert isinstance(event, AssetReady)
        assert asset.is_ready
        assert asset.ready_at == NOW

    def test_transient_failures_fail_the_asset_after_the_last_attempt(self) -> None:
        asset = announced()
        asset.complete_upload(1234, NOW)
        for _ in range(MAX_PROCESSING_ATTEMPTS - 1):
            assert (
                asset.record_failure(
                    code=FailureCode.PROCESSING_ERROR, error="timeout", permanent=False, now=NOW
                )
                is None
            )
            assert asset.status is AssetStatus.UPLOADED
        event = asset.record_failure(
            code=FailureCode.PROCESSING_ERROR, error="timeout", permanent=False, now=NOW
        )
        assert isinstance(event, AssetFailed)
        assert event.failure_code is FailureCode.PROCESSING_ERROR
        assert asset.status is AssetStatus.FAILED
        assert asset.attempts == MAX_PROCESSING_ATTEMPTS

    def test_a_permanent_failure_ends_processing_at_once(self) -> None:
        asset = announced()
        asset.complete_upload(1234, NOW)
        event = asset.record_failure(
            code=FailureCode.UNSUPPORTED_FORMAT, error="x" * 5000, permanent=True, now=NOW
        )
        assert isinstance(event, AssetFailed)
        assert asset.status is AssetStatus.FAILED
        assert asset.last_error is not None
        assert len(asset.last_error) == 1000

    def test_reprocess_starts_over_from_failed_or_ready(self) -> None:
        asset = announced()
        with pytest.raises(InvalidAssetStateError):
            asset.reprocess(NOW)
        asset.complete_upload(1234, NOW)
        asset.record_failure(code=FailureCode.UNREADABLE, error="broken", permanent=True, now=NOW)
        assert isinstance(asset.reprocess(NOW), AssetUploaded)
        assert (asset.status, asset.attempts, asset.failure_code) == (
            AssetStatus.UPLOADED,
            0,
            None,
        )

    def test_tickets_go_stale_after_a_day(self) -> None:
        asset = announced()
        assert not asset.is_stale_upload(NOW + STALE_UPLOAD_AGE - timedelta(seconds=1))
        assert asset.is_stale_upload(NOW + STALE_UPLOAD_AGE)
        asset.complete_upload(1234, NOW)
        assert not asset.is_stale_upload(NOW + STALE_UPLOAD_AGE * 2)

    def test_ready_and_failed_reach_the_admin_area(self) -> None:
        staff_types = event_registry.event_types_for("staff")
        assert {"media.asset.ready", "media.asset.failed"} <= set(staff_types)
        assert "media.asset.uploaded" not in staff_types
        failed = AssetFailed(
            aggregate_id=uuid4(), occurred_at=NOW, failure_code=FailureCode.TOO_SMALL
        )
        assert failed.public_payload() == {
            "asset_id": str(failed.aggregate_id),
            "failure_code": "too_small",
        }


class TestRenditionPlan:
    def test_a_large_photo_gets_every_size(self) -> None:
        planned = {p.name: p for p in plan_renditions(4032, 3024)}
        assert set(planned) == {"thumb", "sm", "md", "lg", "xl", "og"}
        assert planned["thumb"] == PlannedRendition("thumb", 256, 256, cropped=True)
        assert planned["md"] == PlannedRendition("md", 960, 720, cropped=False)
        assert planned["xl"] == PlannedRendition("xl", 2400, 1800, cropped=False)
        assert planned["og"] == PlannedRendition("og", 1200, 630, cropped=True)

    def test_nothing_is_scaled_up(self) -> None:
        names = [p.name for p in plan_renditions(1000, 800)]
        assert names == ["thumb", "sm", "md"]

    def test_a_narrow_original_keeps_its_own_width(self) -> None:
        assert plan_renditions(300, 400) == [
            PlannedRendition("thumb", 256, 256, cropped=True),
            PlannedRendition("sm", 300, 400, cropped=False),
        ]

    def test_og_needs_the_whole_box(self) -> None:
        assert "og" not in [p.name for p in plan_renditions(2000, 600)]
        assert "og" in [p.name for p in plan_renditions(1200, 630)]

    def test_too_small_originals_are_a_caller_error(self) -> None:
        with pytest.raises(ValueError, match="256"):
            plan_renditions(255, 1000)

    def test_storage_keys_carry_a_content_hash(self) -> None:
        asset_id = uuid4()
        key = storage_key(asset_id, "md", "1a2b3c4d5e6f", RenditionFormat.AVIF)
        assert key == f"{asset_id}/md-1a2b3c4d.avif"
        assert RenditionFormat.WEBP.mime_type == "image/webp"


def test_the_contract_hands_out_the_domain_events() -> None:
    from modellbahn.modules.media.contracts import events  # noqa: PLC0415

    assert events.AssetReady is AssetReady
    assert events.AssetStatus is AssetStatus
