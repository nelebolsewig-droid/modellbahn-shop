"""Media of the admin area: ``/api/v1/admin/media`` (upload tickets, state, deletion)."""

from uuid import UUID

from fastapi import APIRouter, Response, status

from modellbahn.modules.media.api.deps import MediaEditor, MediaServiceDep, PublicBaseUrl
from modellbahn.modules.media.api.errors import ACCESS, NOT_FOUND
from modellbahn.modules.media.api.schemas import AssetOut, UploadRequestIn, UploadTicketOut
from modellbahn.platform.errors import problems

router = APIRouter(prefix="/admin/media", tags=["admin-media"])


@router.post(
    "/uploads",
    operation_id="requestMediaUpload",
    summary="Announce an image and get a signed upload URL",
    responses=problems(ACCESS),
)
async def request_upload(
    body: UploadRequestIn, staff: MediaEditor, service: MediaServiceDep, base_url: PublicBaseUrl
) -> UploadTicketOut:
    """PUT the file to ``upload.url`` within 15 minutes, then call ``complete``.

    A file whose SHA-256 is already stored returns that asset and ``upload: null``.
    """
    ticket = await service.request_upload(
        filename=body.filename,
        mime_type=body.mime_type,
        size_bytes=body.size_bytes,
        sha256=body.sha256,
        uploaded_by=staff.id,
    )
    return UploadTicketOut.from_ticket(ticket, public_base_url=base_url)


@router.post(
    "/{asset_id}/complete",
    operation_id="completeMediaUpload",
    summary="Finish an upload and start processing",
    responses=problems({**ACCESS, **NOT_FOUND, 409: ["upload_missing", "upload_size_mismatch"]}),
)
async def complete_upload(
    asset_id: UUID, _: MediaEditor, service: MediaServiceDep, base_url: PublicBaseUrl
) -> AssetOut:
    """The worker renders the sizes; ``media.asset.ready`` arrives on the event stream."""
    asset = await service.complete_upload(asset_id)
    return AssetOut.from_asset(asset, public_base_url=base_url)


@router.get(
    "/{asset_id}",
    operation_id="getMediaAsset",
    summary="State, facts and rendered sizes of an asset",
    responses=problems({**ACCESS, **NOT_FOUND}, unsafe=False),
)
async def get_asset(
    asset_id: UUID, _: MediaEditor, service: MediaServiceDep, base_url: PublicBaseUrl
) -> AssetOut:
    return AssetOut.from_asset(await service.get(asset_id), public_base_url=base_url)


@router.post(
    "/{asset_id}/reprocess",
    status_code=status.HTTP_202_ACCEPTED,
    operation_id="reprocessMediaAsset",
    summary="Render the sizes again",
    responses=problems({**ACCESS, **NOT_FOUND, 409: ["invalid_asset_state"]}),
)
async def reprocess_asset(
    asset_id: UUID, _: MediaEditor, service: MediaServiceDep, base_url: PublicBaseUrl
) -> AssetOut:
    """For failed or ready assets; the result arrives as ``media.asset.ready`` or ``failed``."""
    return AssetOut.from_asset(await service.reprocess(asset_id), public_base_url=base_url)


@router.delete(
    "/{asset_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    operation_id="deleteMediaAsset",
    summary="Delete an asset that nothing uses",
    responses=problems({**ACCESS, **NOT_FOUND, 409: ["asset_in_use"]}),
)
async def delete_asset(asset_id: UUID, _: MediaEditor, service: MediaServiceDep) -> None:
    """The files are removed from the storage shortly after."""
    await service.delete(asset_id)
