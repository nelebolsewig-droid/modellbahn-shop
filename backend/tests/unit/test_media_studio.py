"""The photo studio: differing photo-box shots come out as one row of product photos."""

import io

import numpy as np
import pytest
from PIL import Image, ImageDraw

from modellbahn.modules.media.domain import studio as frame
from modellbahn.modules.media.domain.model import Asset, AssetKind, AssetStatus
from modellbahn.modules.media.domain.studio import Box, place, trustworthy
from modellbahn.modules.media.infrastructure.imaging import STAGE_GROUND, PillowImageProcessor
from modellbahn.modules.media.infrastructure.studio import FloatImage, PhotoStudio
from tests.support import NOW
from tests.unit.test_media_domain import announced, details

MODEL_COLOUR = (190, 70, 30)


class ColourSegmenter:
    """Stands in for the neural cut-out: the model is what has the model's colour."""

    def matte(self, image: Image.Image) -> FloatImage:
        pixels = np.asarray(image.convert("RGB"), dtype=np.float32)
        distance = np.abs(pixels / np.maximum(pixels.sum(-1, keepdims=True), 1) - 0.33).max(-1)
        return (distance > 0.12).astype(np.float32)


class HazeSegmenter:
    """A cut-out that is unsure everywhere, as with a photo that shows no single model."""

    def matte(self, image: Image.Image) -> FloatImage:
        return np.full((image.height, image.width), 0.4, dtype=np.float32)


class NothingSegmenter:
    def matte(self, image: Image.Image) -> FloatImage:
        return np.zeros((image.height, image.width), dtype=np.float32)


def shot(
    backdrop: tuple[int, int, int],
    box: tuple[int, int, int, int],
    *,
    size: tuple[int, int] = (1200, 900),
    tint: tuple[float, float, float] = (1.0, 1.0, 1.0),
) -> Image.Image:
    """A model (a coloured block) in a photo box whose light has a ``tint``."""
    image = Image.new("RGB", size, backdrop)
    ImageDraw.Draw(image).rectangle(box, fill=MODEL_COLOUR)
    pixels = np.asarray(image, dtype=np.float32) * np.asarray(tint, dtype=np.float32)
    return Image.fromarray(np.clip(pixels, 0, 255).astype(np.uint8))


def model_box(staged: Image.Image) -> tuple[int, int, int, int]:
    """Where the model itself (not its shadow) stands in a staged photo."""
    pixels = np.asarray(staged.convert("RGBA")).astype(int)
    model = (pixels[..., 3] > 200) & (pixels[..., 0] - pixels[..., 2] > 60)
    rows = np.flatnonzero(model.any(axis=1))
    columns = np.flatnonzero(model.any(axis=0))
    return int(columns[0]), int(rows[0]), int(columns[-1]) + 1, int(rows[-1]) + 1


def model_colour(staged: Image.Image) -> tuple[int, ...]:
    left, top, right, bottom = model_box(staged)
    centre = staged.convert("RGB").getpixel(((left + right) // 2, (top + bottom) // 2))
    assert isinstance(centre, tuple)
    return centre


@pytest.fixture(scope="module")
def studio() -> PhotoStudio:
    return PhotoStudio(ColourSegmenter())


class TestFrame:
    def test_wide_model_fills_the_width_and_stands_on_the_line(self) -> None:
        placed = place(Box(0, 0, 1000, 200))
        assert placed.width == round(frame.CANVAS * frame.BOX_WIDTH)
        assert placed.y + placed.height == round(frame.CANVAS * frame.STANDLINE)
        assert placed.x == (frame.CANVAS - placed.width) // 2

    def test_tall_model_is_limited_by_the_height(self) -> None:
        placed = place(Box(0, 0, 200, 1000))
        assert placed.height == round(frame.CANVAS * frame.BOX_HEIGHT)
        assert placed.y + placed.height == round(frame.CANVAS * frame.STANDLINE)

    def test_empty_box_is_refused(self) -> None:
        with pytest.raises(ValueError, match="empty"):
            place(Box(5, 5, 5, 9))

    @pytest.mark.parametrize(
        ("subject", "edges", "expected"),
        [(100_000, 0, True), (100, 0, False), (950_000, 0, False), (100_000, 3, False)],
    )
    def test_only_a_plausible_cut_out_is_trusted(
        self, subject: int, edges: int, expected: bool
    ) -> None:
        assert trustworthy(subject, 1_000_000, edges) is expected


class TestStudio:
    def test_differing_shots_stand_in_one_row(self, studio: PhotoStudio) -> None:
        """Small and off-centre, or large and low: same size, same line, same centre."""
        small = studio.finish(shot((235, 235, 235), (150, 200, 550, 400))).image
        large = studio.finish(shot((200, 200, 200), (500, 500, 1100, 800))).image
        assert small is not None
        assert large is not None
        assert small.size == large.size == (frame.CANVAS, frame.CANVAS)
        assert small.mode == "RGBA"
        first, second = model_box(small), model_box(large)
        assert all(abs(a - b) <= 4 for a, b in zip(first, second, strict=True))
        assert abs(first[3] - round(frame.CANVAS * frame.STANDLINE)) <= 3
        assert abs((first[0] + first[2]) / 2 - frame.CANVAS / 2) <= 3

    def test_colour_cast_and_exposure_are_evened_out(self, studio: PhotoStudio) -> None:
        """The same model under warm, dim light and under cool, bright light."""
        box = (300, 300, 900, 600)
        warm = studio.finish(shot((235, 235, 235), box, tint=(0.85, 0.78, 0.66))).image
        cool = studio.finish(shot((235, 235, 235), box, tint=(0.85, 0.95, 1.0))).image
        assert warm is not None
        assert cool is not None
        assert all(
            abs(a - b) <= 12 for a, b in zip(model_colour(warm), model_colour(cool), strict=True)
        )

    def test_backdrop_is_gone_and_a_shadow_lies_under_the_model(self, studio: PhotoStudio) -> None:
        staged = studio.finish(shot((230, 230, 230), (300, 300, 900, 600))).image
        assert staged is not None
        alpha = np.asarray(staged.getchannel("A"))
        assert alpha[10, 10] == 0
        assert alpha[frame.CANVAS // 4, frame.CANVAS // 2] == 0
        left, _, right, bottom = model_box(staged)
        under = alpha[bottom + 12, (left + right) // 2]
        assert 0 < under < 255

    def test_the_shadow_in_the_photo_is_kept_and_a_darker_wall_is_not(
        self, studio: PhotoStudio
    ) -> None:
        photo = shot((230, 230, 230), (300, 300, 900, 600))
        draw = ImageDraw.Draw(photo)
        # A wall behind the model, darker than the floor; the shadow under its right half.
        draw.rectangle((0, 0, 1200, 380), fill=(205, 205, 205))
        draw.ellipse((600, 560, 1000, 660), fill=(150, 150, 150))
        draw.rectangle((300, 300, 900, 600), fill=MODEL_COLOUR)
        staged = studio.finish(photo).image
        assert staged is not None
        alpha = np.asarray(staged.getchannel("A"))
        left, top, right, bottom = model_box(staged)
        scale = (right - left) / 600
        assert alpha[bottom + round(30 * scale), right - round(100 * scale)] > 40
        assert alpha[bottom + round(30 * scale), left + round(100 * scale)] < 8
        assert alpha[top + round(20 * scale), right + round(20 * scale)] < 8

    def test_black_tyres_in_the_shadow_stay_on_the_model(self, studio: PhotoStudio) -> None:
        photo = shot((230, 230, 230), (300, 300, 900, 600))
        draw = ImageDraw.Draw(photo)
        # Two tyres under the car, which the cut-out takes for shadow, and a black
        # speck of dirt away from the model, which is none of the model's.
        draw.ellipse((360, 560, 460, 660), fill=(4, 4, 4))
        draw.ellipse((740, 560, 840, 660), fill=(4, 4, 4))
        draw.ellipse((580, 650, 620, 690), fill=(4, 4, 4))
        draw.rectangle((300, 300, 900, 600), fill=MODEL_COLOUR)
        staged = studio.finish(photo).image
        assert staged is not None
        pixels = np.asarray(staged.convert("RGBA")).astype(int)
        left, _top, right, bottom = model_box(staged)
        scale = (right - left) / 600
        for x in (410, 790):
            tyre = pixels[bottom + round(40 * scale), left + round((x - 300) * scale)]
            assert tyre[3] > 240
            assert tyre[:3].max() < 60
        speck = pixels[bottom + round(70 * scale), left + round(300 * scale)]
        assert speck[3] < 160

    def test_in_a_dark_room_nothing_dark_is_added(self, studio: PhotoStudio) -> None:
        photo = shot((60, 60, 60), (300, 300, 900, 600))
        draw = ImageDraw.Draw(photo)
        draw.ellipse((360, 560, 460, 660), fill=(4, 4, 4))
        draw.rectangle((300, 300, 900, 600), fill=MODEL_COLOUR)
        staged = studio.finish(photo).image
        assert staged is not None
        pixels = np.asarray(staged.convert("RGBA")).astype(int)
        left, _top, right, bottom = model_box(staged)
        scale = (right - left) / 600
        assert pixels[bottom + round(40 * scale), left + round(110 * scale), 3] < 160

    def test_photo_without_a_model_is_left_alone(self) -> None:
        result = PhotoStudio(NothingSegmenter()).finish(shot((230, 230, 230), (0, 0, 0, 0)))
        assert result.image is None
        assert result.reason

    def test_photo_the_cut_out_is_unsure_about_is_left_alone(self) -> None:
        result = PhotoStudio(HazeSegmenter()).finish(shot((230, 230, 230), (300, 300, 900, 600)))
        assert result.image is None
        assert result.reason


class TestProcessor:
    @staticmethod
    def jpeg(image: Image.Image) -> bytes:
        buffer = io.BytesIO()
        image.save(buffer, "JPEG", quality=92)
        return buffer.getvalue()

    def test_staged_photo_is_square_and_transparent(self) -> None:
        processor = PillowImageProcessor(studio=PhotoStudio(ColourSegmenter()))
        data = self.jpeg(shot((230, 230, 230), (300, 300, 900, 600)))
        result = processor.process(data, studio=True)
        assert result.studio_applied
        assert (result.width, result.height) == (frame.CANVAS, frame.CANVAS)
        # The placeholder colour is the stage, so nothing flashes while the photo loads.
        ground = "#{:02x}{:02x}{:02x}".format(*STAGE_GROUND)
        assert all(
            abs(int(result.dominant_color[i : i + 2], 16) - int(ground[i : i + 2], 16)) <= 6
            for i in (1, 3, 5)
        )
        md = next(r for r in result.renditions if r.name == "md" and r.format.value == "webp")
        assert Image.open(io.BytesIO(md.data)).mode == "RGBA"
        # The link preview has no page behind it and stands on the stage colour itself.
        og = next(r for r in result.renditions if r.name == "og" and r.format.value == "webp")
        preview = Image.open(io.BytesIO(og.data)).convert("RGB")
        corner = preview.getpixel((5, 5))
        assert isinstance(corner, tuple)
        assert all(abs(a - b) <= 6 for a, b in zip(corner, STAGE_GROUND, strict=True))

    def test_a_picture_already_cut_out_gets_no_dark_box(self) -> None:
        # A render on a transparent ground: its hidden pixels are black.
        rgba = Image.new("RGBA", (1200, 900), (0, 0, 0, 0))
        ImageDraw.Draw(rgba).rectangle((300, 300, 900, 600), fill=(*MODEL_COLOUR, 255))
        buffer = io.BytesIO()
        rgba.save(buffer, "PNG")
        processor = PillowImageProcessor(studio=PhotoStudio(ColourSegmenter()))
        result = processor.process(buffer.getvalue(), studio=True)
        assert result.studio_applied
        md = next(r for r in result.renditions if r.name == "md" and r.format.value == "webp")
        staged = np.asarray(Image.open(io.BytesIO(md.data)).convert("RGBA"))
        model = (staged[..., 3] > 200) & (staged[..., 0].astype(int) - staged[..., 2] > 60)
        rows = np.flatnonzero(model.any(axis=1))
        columns = np.flatnonzero(model.any(axis=0))
        # Beside the model, above its floor line, the stage stays clear.
        middle = (rows[0] + rows[-1]) // 2
        above = staged[rows[0] : middle, : columns[0] - 20, 3]
        assert int(above.max()) < 40

    def test_switched_off_or_without_studio_the_photo_stays_as_uploaded(self) -> None:
        data = self.jpeg(shot((230, 230, 230), (300, 300, 900, 600)))
        with_studio = PillowImageProcessor(studio=PhotoStudio(ColourSegmenter()))
        plain = with_studio.process(data, studio=False)
        assert not plain.studio_applied
        assert (plain.width, plain.height) == (1200, 900)
        missing = PillowImageProcessor().process(data, studio=True)
        assert not missing.studio_applied

    def test_photo_without_a_model_is_rendered_as_uploaded(self) -> None:
        processor = PillowImageProcessor(studio=PhotoStudio(NothingSegmenter()))
        result = processor.process(self.jpeg(shot((230, 230, 230), (0, 0, 0, 0))), studio=True)
        assert not result.studio_applied
        assert (result.width, result.height) == (1200, 900)


class TestSwitch:
    def test_new_uploads_go_through_the_studio(self) -> None:
        assert announced().studio is True
        assert announced().kind is AssetKind.IMAGE

    def test_switching_a_ready_photo_renders_it_again(self) -> None:
        asset = ready()
        event = asset.set_studio(False, NOW)
        assert event is not None
        assert asset.studio is False
        assert asset.status is AssetStatus.UPLOADED

    def test_switching_to_the_same_setting_does_nothing(self) -> None:
        asset = ready()
        assert asset.set_studio(True, NOW) is None
        assert asset.status is AssetStatus.READY

    def test_a_photo_still_uploading_only_remembers_the_setting(self) -> None:
        asset = announced()
        assert asset.set_studio(False, NOW) is None
        assert asset.studio is False
        assert asset.status is AssetStatus.PENDING_UPLOAD


def ready() -> Asset:
    asset = announced()
    asset.complete_upload(asset.size_bytes, NOW)
    asset.mark_ready(image=details(asset), renditions=[], now=NOW)
    return asset
