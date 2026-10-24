"""Image processing with Pillow: what comes out, and what is refused."""

import base64
import io

import pytest
from PIL import Image, ImageCms

from modellbahn.modules.media.domain.errors import FailureCode, ImageRejectedError
from modellbahn.modules.media.domain.renditions import RenditionFormat
from modellbahn.modules.media.infrastructure.imaging import PillowImageProcessor
from tests.media_support import photo, png_claiming_size


@pytest.fixture(scope="module")
def processor() -> PillowImageProcessor:
    return PillowImageProcessor()


def decoded(data: bytes) -> Image.Image:
    image = Image.open(io.BytesIO(data))
    image.load()
    return image


def test_renders_every_planned_size_in_both_formats(processor: PillowImageProcessor) -> None:
    result = processor.process(photo(1300, 700))
    produced = {(r.name, r.format) for r in result.renditions}
    assert produced == {
        (name, fmt)
        for name in ("thumb", "sm", "md", "og")
        for fmt in (RenditionFormat.WEBP, RenditionFormat.AVIF)
    }
    for rendition in result.renditions:
        image = decoded(rendition.data)
        assert image.format == rendition.format.value.upper()
        assert image.size == (rendition.width, rendition.height)
    assert (result.width, result.height) == (1300, 700)


def test_applies_the_exif_rotation_and_drops_all_metadata(
    processor: PillowImageProcessor,
) -> None:
    # Orientation 6: the camera was turned, the pixels are stored lying on their side.
    result = processor.process(photo(800, 600, orientation=6, with_gps=True))
    assert (result.width, result.height) == (600, 800)
    for rendition in result.renditions:
        image = decoded(rendition.data)
        assert not image.getexif(), f"{rendition.name}.{rendition.format} kept EXIF data"
        assert "icc_profile" not in image.info
        assert b"Testkamera" not in rendition.data


def test_placeholder_colour_and_hash(processor: PillowImageProcessor) -> None:
    result = processor.process(photo(640, 480, colour=(200, 40, 40)))
    assert result.lqip.startswith("data:image/webp;base64,")
    tiny = decoded(base64.b64decode(result.lqip.split(",", 1)[1]))
    assert tiny.size == (16, 12)
    # Three quarters of the photo are red, one quarter is the dark stripe.
    red, green, blue = (int(result.dominant_color[i : i + 2], 16) for i in (1, 3, 5))
    assert red > 150 > green
    assert blue < 100
    assert -(2**63) <= result.phash < 2**63


def test_similar_images_have_similar_hashes(processor: PillowImageProcessor) -> None:
    original = processor.process(photo(1200, 900)).phash
    smaller = processor.process(photo(600, 450, image_format="PNG")).phash
    different = processor.process(photo(900, 1200, orientation=8)).phash
    assert bin((original ^ smaller) & (2**64 - 1)).count("1") <= 4
    assert bin((original ^ different) & (2**64 - 1)).count("1") > 10


def test_transparency_survives(processor: PillowImageProcessor) -> None:
    result = processor.process(photo(400, 400, image_format="PNG", mode="RGBA"))
    webp = next(r for r in result.renditions if r.format is RenditionFormat.WEBP)
    assert decoded(webp.data).mode == "RGBA"


@pytest.mark.parametrize("image_format", ["PNG", "WEBP", "AVIF"])
def test_reads_the_accepted_formats(processor: PillowImageProcessor, image_format: str) -> None:
    result = processor.process(photo(500, 300, image_format=image_format))
    assert (result.width, result.height) == (500, 300)


def test_reads_heic_from_iphones(processor: PillowImageProcessor) -> None:
    pillow_heif = pytest.importorskip("pillow_heif")
    buffer = io.BytesIO()
    Image.new("RGB", (512, 384), (30, 90, 160)).save(buffer, "HEIF")
    assert pillow_heif.is_supported(buffer.getvalue())
    result = processor.process(buffer.getvalue())
    assert (result.width, result.height) == (512, 384)


@pytest.mark.parametrize(
    ("data", "code"),
    [
        (b"%PDF-1.7 not an image", FailureCode.UNSUPPORTED_FORMAT),
        (photo(640, 480, image_format="GIF"), FailureCode.UNSUPPORTED_FORMAT),
        (photo(640, 480)[:2000], FailureCode.UNREADABLE),
        (photo(255, 1000), FailureCode.TOO_SMALL),
        (png_claiming_size(20_000, 20_000), FailureCode.TOO_MANY_PIXELS),
    ],
    ids=["pdf", "gif", "truncated", "too-small", "decompression-bomb"],
)
def test_refuses_what_is_no_usable_image(
    processor: PillowImageProcessor, data: bytes, code: FailureCode
) -> None:
    with pytest.raises(ImageRejectedError) as caught:
        processor.process(data)
    assert caught.value.code is code


def test_converts_embedded_colour_profiles_to_srgb(processor: PillowImageProcessor) -> None:
    profile = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
    buffer = io.BytesIO()
    Image.new("RGB", (400, 300), (10, 120, 200)).save(buffer, "JPEG", icc_profile=profile)
    result = processor.process(buffer.getvalue())
    for rendition in result.renditions:
        assert "icc_profile" not in decoded(rendition.data).info


def test_converts_cmyk_print_files(processor: PillowImageProcessor) -> None:
    buffer = io.BytesIO()
    Image.new("CMYK", (400, 300), (0, 80, 160, 20)).save(buffer, "JPEG")
    result = processor.process(buffer.getvalue())
    assert decoded(result.renditions[0].data).mode == "RGB"


def test_an_unusable_profile_counts_as_srgb(processor: PillowImageProcessor) -> None:
    buffer = io.BytesIO()
    Image.new("RGB", (300, 300), (90, 90, 90)).save(buffer, "PNG", icc_profile=b"kaputt")
    assert processor.process(buffer.getvalue()).width == 300
