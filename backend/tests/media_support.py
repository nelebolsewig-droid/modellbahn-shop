"""Test doubles and sample files for the media and catalogue tests."""

import hashlib
import io
import struct
import zlib
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import timedelta
from uuid import UUID

from PIL import Image

from modellbahn.modules.media.application.services import MediaService
from modellbahn.modules.media.domain.model import Asset, original_key

# EXIF tags (TIFF numbering).
ORIENTATION = 0x0112
GPS_INFO = 0x8825
MAKE = 0x010F


@dataclass
class StoredFile:
    data: bytes
    content_type: str
    cache_control: str | None = None


@dataclass
class InMemoryMediaStorage:
    """:class:`MediaStorage` in a dict; "uploads" are put in place with :meth:`upload`."""

    private: dict[str, bytes] = field(default_factory=dict)
    public: dict[str, StoredFile] = field(default_factory=dict)
    presigned: list[dict[str, object]] = field(default_factory=list)
    fail_reads: int = 0

    def presign_original_upload(
        self, key: str, *, content_type: str, content_length: int, expires_in: timedelta
    ) -> str:
        self.presigned.append(
            {
                "key": key,
                "content_type": content_type,
                "content_length": content_length,
                "expires_in": expires_in,
            }
        )
        return f"https://storage.test/mb-media-private/{key}?signature=test"

    def upload(self, asset_id: UUID, data: bytes) -> None:
        """What the browser's PUT would do."""
        self.private[original_key(asset_id)] = data

    async def original_size(self, key: str) -> int | None:
        data = self.private.get(key)
        return None if data is None else len(data)

    async def read_original(self, key: str, *, max_bytes: int) -> bytes:
        if self.fail_reads:
            self.fail_reads -= 1
            msg = "storage unreachable"
            raise ConnectionError(msg)
        data = self.private[key]
        if len(data) > max_bytes:
            msg = "too large"
            raise ValueError(msg)
        return data

    async def publish_rendition(self, key: str, data: bytes, *, content_type: str) -> None:
        self.public[key] = StoredFile(data, content_type)

    async def delete_renditions(self, keys: list[str]) -> None:
        for key in keys:
            self.public.pop(key, None)

    async def delete_files(self, asset_id: UUID) -> None:
        self.private.pop(original_key(asset_id), None)
        for key in [k for k in self.public if k.startswith(f"{asset_id}/")]:
            del self.public[key]


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def photo(
    width: int = 640,
    height: int = 480,
    *,
    colour: tuple[int, int, int] = (180, 60, 40),
    image_format: str = "JPEG",
    orientation: int | None = None,
    with_gps: bool = False,
    mode: str = "RGB",
) -> bytes:
    """A photo with a stripe (so orientation is visible) and optional EXIF data."""
    fill: tuple[int, ...] = (*colour, 255) if mode == "RGBA" else colour
    image = Image.new(mode, (width, height), fill)
    # With an alpha channel the stripe is transparent.
    stripe: tuple[int, ...] = (20, 20, 20, 0) if mode == "RGBA" else (20, 20, 20)
    for x in range(width // 4):
        for y in range(height):
            image.putpixel((x, y), stripe)
    exif = Image.Exif()
    if orientation is not None:
        exif[ORIENTATION] = orientation
    if with_gps:
        exif[MAKE] = "Testkamera"
        exif[GPS_INFO] = {1: "N", 2: (51.0, 47.0, 0.0), 3: "E", 4: (10.0, 25.0, 0.0)}
    buffer = io.BytesIO()
    options: dict[str, object] = {}
    if len(exif):
        options["exif"] = exif
    image.save(buffer, image_format, **options)
    return buffer.getvalue()


def png_claiming_size(width: int, height: int) -> bytes:
    """A tiny valid PNG whose header claims ``width`` x ``height`` pixels."""
    buffer = io.BytesIO()
    Image.new("RGB", (1, 1)).save(buffer, "PNG")
    data = bytearray(buffer.getvalue())
    # Signature (8) + length (4) + "IHDR" (4), then width, height and the rest of IHDR.
    start = 16
    data[start : start + 8] = struct.pack(">II", width, height)
    ihdr = bytes(data[12 : start + 13])
    data[start + 13 : start + 17] = struct.pack(">I", zlib.crc32(ihdr) & 0xFFFFFFFF)
    return bytes(data)


async def uploaded_image(
    media: MediaService, storage: InMemoryMediaStorage, data: bytes | None = None
) -> Asset:
    """An image whose upload is complete; the worker has not processed it yet."""
    content = data if data is not None else photo()
    ticket = await media.request_upload(
        filename="foto.jpg",
        mime_type="image/jpeg",
        size_bytes=len(content),
        sha256=sha256(content),
        uploaded_by=None,
    )
    storage.upload(ticket.asset.id, content)
    return await media.complete_upload(ticket.asset.id)


async def ready_image(
    media: MediaService,
    storage: InMemoryMediaStorage,
    deliver: Callable[[], Awaitable[int]],
    data: bytes | None = None,
) -> Asset:
    """An image the worker has rendered."""
    asset = await uploaded_image(media, storage, data)
    await deliver()
    ready = await media.get(asset.id)
    assert ready.is_ready, ready.status
    return ready
