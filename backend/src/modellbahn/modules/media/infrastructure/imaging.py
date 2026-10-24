"""Image processing with Pillow: decode, check, normalise and render every size.

The original is foreign data. Its format is taken from the bytes (magic numbers),
not from the announced type; the pixel count is checked before anything is decoded.
The rendered sizes carry no metadata at all: the EXIF orientation is applied to the
pixels, then EXIF (with GPS position and camera serial) and colour profiles are left
behind, and the pixels are converted to sRGB, which every browser assumes.
"""

import base64
import io
import warnings
from typing import Final

import pillow_heif
from PIL import Image, ImageCms, ImageOps, UnidentifiedImageError

from modellbahn.modules.media.application.ports import EncodedRendition, ProcessedImage
from modellbahn.modules.media.domain.errors import FailureCode, ImageRejectedError
from modellbahn.modules.media.domain.model import IMAGE_MAX_PIXELS
from modellbahn.modules.media.domain.renditions import (
    MIN_EDGE,
    RENDITION_FORMATS,
    PlannedRendition,
    RenditionFormat,
    plan_renditions,
)

# HEIC is what iPhones take photos in.
pillow_heif.register_heif_opener()
# Pillow's own guard (a warning, then an error at twice the limit) at our limit; the
# explicit check below rejects such images before they are decoded anyway.
Image.MAX_IMAGE_PIXELS = IMAGE_MAX_PIXELS

ACCEPTED_FORMATS: Final = ("JPEG", "PNG", "WEBP", "AVIF", "HEIF")
WEBP_QUALITY: Final = 80
# AVIF looks at quality 60 about like WebP at 80, and is smaller.
AVIF_QUALITY: Final = 60
AVIF_SPEED: Final = 7
LQIP_WIDTH: Final = 16
LQIP_QUALITY: Final = 40
_DOMINANT_SAMPLE: Final = 64
_DOMINANT_COLOURS: Final = 6
_SRGB: Final = ImageCms.createProfile("sRGB")


class PillowImageProcessor:
    """:class:`~modellbahn.modules.media.application.ports.ImageProcessor` with Pillow."""

    def process(self, data: bytes) -> ProcessedImage:
        image = _open(data)
        width, height = image.size
        if min(width, height) < MIN_EDGE:
            msg = f"{width} x {height} px, at least {MIN_EDGE} px needed on the shorter side"
            raise ImageRejectedError(FailureCode.TOO_SMALL, msg)
        renditions = [
            encoded
            for planned in plan_renditions(width, height)
            for encoded in _render(image, planned)
        ]
        return ProcessedImage(
            width=width,
            height=height,
            dominant_color=_dominant_color(image),
            lqip=_lqip(image),
            phash=_difference_hash(image),
            renditions=renditions,
        )


def _open(data: bytes) -> Image.Image:
    """Decode the first frame, upright and in sRGB; refuse what is no usable image."""
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            image = Image.open(io.BytesIO(data), formats=ACCEPTED_FORMATS)
            pixels = image.size[0] * image.size[1]
            if pixels > IMAGE_MAX_PIXELS:
                msg = f"{image.size[0]} x {image.size[1]} px exceeds {IMAGE_MAX_PIXELS} pixels"
                raise ImageRejectedError(FailureCode.TOO_MANY_PIXELS, msg)
            # Animated images: the first frame is the product photo.
            image.seek(0)
            image.load()
    except UnidentifiedImageError as exc:
        raise ImageRejectedError(FailureCode.UNSUPPORTED_FORMAT, str(exc)) from exc
    except (Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise ImageRejectedError(FailureCode.TOO_MANY_PIXELS, str(exc)) from exc
    except (OSError, SyntaxError, ValueError) as exc:
        # Truncated or damaged files surface as one of these from the decoders.
        raise ImageRejectedError(FailureCode.UNREADABLE, f"{type(exc).__name__}: {exc}") from exc
    upright = ImageOps.exif_transpose(image)
    normalised = _to_srgb(upright, image.info.get("icc_profile"))
    # Nothing of the original's metadata travels on: no EXIF, XMP or profile.
    normalised.info = {}
    return normalised


def _to_srgb(image: Image.Image, icc_profile: object) -> Image.Image:
    has_alpha = image.mode in {"RGBA", "LA", "PA"} or (
        image.mode == "P" and "transparency" in image.info
    )
    target_mode = "RGBA" if has_alpha else "RGB"
    if isinstance(icc_profile, bytes) and icc_profile:
        try:
            source = ImageCms.ImageCmsProfile(io.BytesIO(icc_profile))
            if image.mode not in {"RGB", "RGBA", "CMYK", "L"}:
                image = image.convert(target_mode)
            converted = ImageCms.profileToProfile(
                image, source, _SRGB, outputMode="RGBA" if image.mode == "RGBA" else "RGB"
            )
            if converted is not None:
                return converted.convert(target_mode)
        except (ImageCms.PyCMSError, OSError):
            # An unusable profile: treat the pixels as sRGB, as browsers would.
            pass
    return image.convert(target_mode)


def _render(image: Image.Image, planned: PlannedRendition) -> list[EncodedRendition]:
    size = (planned.width, planned.height)
    if planned.cropped:
        scaled = ImageOps.fit(image, size, Image.Resampling.LANCZOS, centering=(0.5, 0.5))
    elif size == image.size:
        scaled = image
    else:
        scaled = image.resize(size, Image.Resampling.LANCZOS, reducing_gap=3.0)
    return [
        EncodedRendition(
            name=planned.name,
            format=rendition_format,
            width=planned.width,
            height=planned.height,
            data=_encode(scaled, rendition_format),
        )
        for rendition_format in RENDITION_FORMATS
    ]


def _encode(image: Image.Image, rendition_format: RenditionFormat) -> bytes:
    buffer = io.BytesIO()
    if rendition_format is RenditionFormat.WEBP:
        image.save(buffer, "WEBP", quality=WEBP_QUALITY, method=4)
    else:
        image.save(buffer, "AVIF", quality=AVIF_QUALITY, speed=AVIF_SPEED)
    return buffer.getvalue()


def _flattened(image: Image.Image) -> Image.Image:
    """The image on white: transparent parts must not count as black."""
    if image.mode != "RGBA":
        return image.convert("RGB")
    background = Image.new("RGB", image.size, (255, 255, 255))
    background.paste(image, mask=image.getchannel("A"))
    return background


def _lqip(image: Image.Image) -> str:
    """A 16 px wide WebP as data URI; blurred by the browser while scaling it up."""
    height = max(1, round(image.height * LQIP_WIDTH / image.width))
    tiny = _flattened(image).resize((LQIP_WIDTH, height), Image.Resampling.BOX)
    buffer = io.BytesIO()
    tiny.save(buffer, "WEBP", quality=LQIP_QUALITY)
    return "data:image/webp;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")


def _dominant_color(image: Image.Image) -> str:
    """The most frequent of a few representative colours, as ``#rrggbb``."""
    sample = _flattened(image)
    sample.thumbnail((_DOMINANT_SAMPLE, _DOMINANT_SAMPLE), Image.Resampling.BOX)
    palette_image = sample.quantize(colors=_DOMINANT_COLOURS, method=Image.Quantize.MEDIANCUT)
    # A palette image counts palette indices.
    counts = [
        (count, colour)
        for count, colour in palette_image.getcolors() or []
        if isinstance(colour, int)
    ]
    _, index = max(counts, default=(0, 0))
    palette = palette_image.getpalette() or [0, 0, 0]
    red, green, blue = palette[index * 3 : index * 3 + 3]
    return f"#{red:02x}{green:02x}{blue:02x}"


def _difference_hash(image: Image.Image) -> int:
    """64-bit dHash: is each pixel of a 9 x 8 grey version brighter than its right neighbour?

    Similar images differ in few bits (Hamming distance), whatever their size or
    compression. Returned signed, to fit PostgreSQL's bigint.
    """
    grey = _flattened(image).convert("L").resize((9, 8), Image.Resampling.LANCZOS)
    # One byte per pixel in mode "L", row by row.
    pixels = grey.tobytes()
    value = 0
    for row in range(8):
        for column in range(8):
            left = pixels[row * 9 + column]
            right = pixels[row * 9 + column + 1]
            value = (value << 1) | int(left > right)
    return value - (1 << 64) if value >= 1 << 63 else value
