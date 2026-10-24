"""Request and response bodies of the media API (snake_case JSON)."""

from datetime import datetime
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from modellbahn.modules.media.application.services import UploadTicket
from modellbahn.modules.media.domain.errors import FailureCode
from modellbahn.modules.media.domain.model import Asset, AssetKind, AssetStatus
from modellbahn.modules.media.domain.renditions import RenditionFormat


class UploadRequestIn(BaseModel):
    """What the browser knows about a file before uploading it."""

    model_config = ConfigDict(extra="forbid")

    filename: Annotated[str, Field(min_length=1, max_length=1024)]
    mime_type: Annotated[str, Field(min_length=1, max_length=100, examples=["image/jpeg"])]
    size_bytes: Annotated[int, Field(ge=1)]
    # Computed in the browser with Web Crypto; recognises a file that is already stored.
    sha256: Annotated[str, Field(pattern=r"^[0-9a-fA-F]{64}$")]


class RenditionOut(BaseModel):
    name: str = Field(examples=["md"])
    format: RenditionFormat
    width: int
    height: int
    url: str = Field(examples=["/medien/0192f6c3-0000-7000-8000-000000000000/md-1a2b3c4d.webp"])


class ImageFactsOut(BaseModel):
    width: int
    height: int
    dominant_color: str = Field(examples=["#c8c8be"])
    # Tiny blurred placeholder (data URI) for the time the real image loads.
    lqip: str


class AssetOut(BaseModel):
    id: UUID
    kind: AssetKind
    status: AssetStatus
    original_filename: str
    mime_type: str
    size_bytes: int
    failure_code: FailureCode | None
    created_at: datetime
    ready_at: datetime | None
    image: ImageFactsOut | None
    renditions: list[RenditionOut]

    @classmethod
    def from_asset(cls, asset: Asset, *, public_base_url: str) -> Self:
        image = asset.image
        return cls(
            id=asset.id,
            kind=asset.kind,
            status=asset.status,
            original_filename=asset.original_filename,
            mime_type=asset.mime_type,
            size_bytes=asset.size_bytes,
            failure_code=asset.failure_code,
            created_at=asset.created_at,
            ready_at=asset.ready_at,
            image=None
            if image is None
            else ImageFactsOut(
                width=image.width,
                height=image.height,
                dominant_color=image.dominant_color,
                lqip=image.lqip,
            ),
            renditions=[
                RenditionOut(
                    name=rendition.name,
                    format=rendition.format,
                    width=rendition.width,
                    height=rendition.height,
                    url=f"{public_base_url}/{rendition.storage_key}",
                )
                for rendition in asset.renditions
            ],
        )


class UploadOut(BaseModel):
    """Send the file with exactly this method and these headers before ``expires_at``."""

    url: str
    method: Literal["PUT"]
    headers: dict[str, str]
    expires_at: datetime


class UploadTicketOut(BaseModel):
    """``upload`` is null when the same file is already stored: use ``asset`` as it is."""

    asset: AssetOut
    upload: UploadOut | None

    @classmethod
    def from_ticket(cls, ticket: UploadTicket, *, public_base_url: str) -> Self:
        upload = ticket.upload
        return cls(
            asset=AssetOut.from_asset(ticket.asset, public_base_url=public_base_url),
            upload=None
            if upload is None
            else UploadOut(
                url=upload.url,
                method="PUT",
                headers=upload.headers,
                expires_at=upload.expires_at,
            ),
        )
