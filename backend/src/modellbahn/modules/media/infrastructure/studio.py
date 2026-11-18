"""The photo studio: turn a photo-box shot into a uniform product photo.

Steps, all on the worker (ADR 0031):

1. **Cut out** the model with a neural matting model (ISNet, ONNX, on the CPU).
   Specks are dropped, small holes filled, the edge stays soft.
2. **Light** is evened out against the photo box's backdrop, which is white: its colour
   cast is removed (white balance) and its brightness brought to one level, so that
   every photo looks taken under the same lamp. The corrections are capped, a strange
   backdrop (a coloured one from an edit, say) is only partly trusted.
3. **Edge colour**: the backdrop shines through the soft edge; it is taken out again,
   so the model shows no light fringe on the sand of the shop.
4. **Stage**: the model is scaled into a fixed box of a square canvas and stood on one
   line (:mod:`~modellbahn.modules.media.domain.studio`), with a contact shadow and a
   soft floor shadow in espresso. The canvas is transparent: the shop's own stage
   colour shows through, so the photo never has a visible edge.

The result is an RGBA image; the rendition pipeline encodes it as usual.
"""

# ruff: noqa: PLR2004  # image arithmetic: the thresholds are explained where they stand

import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, Protocol

import numpy as np
import structlog
from numpy.typing import NDArray
from PIL import Image, ImageFilter
from scipy import ndimage

from modellbahn.modules.media.domain.studio import (
    CANVAS,
    CROP_MARGIN,
    Box,
    place,
    trustworthy,
)

type FloatImage = NDArray[np.float32]

_logger = structlog.get_logger(__name__)

# Long side the analysis works at: plenty for the 2048 px stage, and fast.
WORK_EDGE: Final = 2600
# Brightness the backdrop is brought to (linear light; about #f0f0f0 in sRGB).
BACKDROP_LEVEL: Final = 0.86
# Caps of the corrections: beyond these a photo is rather left as it is.
MAX_CHANNEL_GAIN: Final = 1.8
MIN_EXPOSURE_GAIN: Final = 0.6
MAX_EXPOSURE_GAIN: Final = 2.4
# A backdrop more colourful than this is not a white photo box: correct only partly.
NEUTRAL_BACKDROP_CHROMA: Final = 0.5
# Share of the found area that may be a mere maybe; real models stay below 0.15.
MAX_UNSURE_SHARE: Final = 0.5
# Espresso #26211e, the ink of the shop, as shadow colour.
SHADOW_RGB: Final = (0x26, 0x21, 0x1E)
CONTACT_SHADOW_OPACITY: Final = 0.5
FLOOR_SHADOW_OPACITY: Final = 0.2


class Segmenter(Protocol):
    def matte(self, image: Image.Image) -> FloatImage:
        """Opacity of the model per pixel (0 backdrop, 1 model), the image's size."""
        ...


@dataclass(frozen=True, slots=True)
class StudioResult:
    """``image`` is the stage photo (RGBA), or ``None`` if no model was found."""

    image: Image.Image | None
    reason: str | None = None


class PhotoStudio:
    """Cut out, correct and stage a model photo. Thread-safe."""

    def __init__(self, segmenter: Segmenter) -> None:
        self._segmenter = segmenter

    def finish(self, image: Image.Image) -> StudioResult:
        work = _downscaled(image.convert("RGB"))
        rgb = _to_float(work)
        matte = self._segmenter.matte(work)
        if _hesitant(matte):
            return StudioResult(None, "the cut-out is unsure what the model is")
        alpha = _clean_matte(matte)
        solid = alpha > 0.5
        subject = _bounding_box(solid)
        total = solid.size
        if subject is None or not trustworthy(
            int(solid.sum()), total, _touched_edges(subject, solid.shape)
        ):
            return StudioResult(None, "no model found against the backdrop")

        linear = _to_linear(rgb)
        backdrop = _backdrop_colour(linear, alpha)
        corrected = _correct_light(linear, backdrop)
        local_backdrop = _local_backdrop(corrected, alpha)

        crop = _expanded(subject, solid.shape, CROP_MARGIN)
        window = (slice(crop.top, crop.bottom), slice(crop.left, crop.right))
        fg = _decontaminate(corrected[window], alpha[window], local_backdrop[window])
        cut = _to_image(_to_srgb(fg), alpha[window])

        inner = Box(
            subject.left - crop.left,
            subject.top - crop.top,
            subject.right - crop.left,
            subject.bottom - crop.top,
        )
        return StudioResult(_stage(cut, inner))


class IsnetSegmenter:
    """Neural cut-out with ISNet (``isnet-general-use``) on onnxruntime.

    The session is opened on first use and shared.
    """

    INPUT_EDGE: Final = 1024
    MEAN: Final = (0.485, 0.456, 0.406)

    def __init__(self, model_path: Path, *, threads: int = 2) -> None:
        self._model_path = model_path
        self._threads = threads
        self._session: Any = None
        self._lock = threading.Lock()
        self._run_lock = threading.Lock()

    def _open(self) -> Any:
        with self._lock:
            if self._session is None:
                import onnxruntime  # noqa: PLC0415  # heavy, only needed by the worker

                options = onnxruntime.SessionOptions()
                options.intra_op_num_threads = self._threads
                options.inter_op_num_threads = 1
                # Give memory back after each photo instead of keeping an arena for good:
                # the worker cuts out a photo now and then, not all day.
                options.enable_cpu_mem_arena = False
                self._session = onnxruntime.InferenceSession(
                    str(self._model_path), options, providers=["CPUExecutionProvider"]
                )
            return self._session

    def matte(self, image: Image.Image) -> FloatImage:
        session = self._open()
        edge = self.INPUT_EDGE
        resized = image.convert("RGB").resize((edge, edge), Image.Resampling.BILINEAR)
        pixels = np.asarray(resized, dtype=np.float32)
        pixels = pixels / max(float(pixels.max()), 1e-6)
        pixels = pixels - np.asarray(self.MEAN, dtype=np.float32)
        tensor = pixels.transpose(2, 0, 1)[None, ...]
        input_name = session.get_inputs()[0].name
        # One photo at a time: a run takes over a gigabyte, several at once would add up.
        with self._run_lock:
            prediction = np.asarray(session.run(None, {input_name: tensor})[0], dtype=np.float32)
        prediction = prediction[0, 0]
        low, high = float(prediction.min()), float(prediction.max())
        prediction = (prediction - low) / max(high - low, 1e-6)
        return _resized(prediction, image.size)


def default_studio(model_path: Path | None) -> PhotoStudio | None:
    """The studio with ISNet, or ``None`` when its model file is not installed.

    Without the studio every photo is rendered as it was uploaded; the worker says so
    once at its start instead of failing every upload.
    """
    if model_path is not None and model_path.is_file():
        return PhotoStudio(IsnetSegmenter(model_path))
    _logger.warning("media.studio_unavailable", model_path=str(model_path) if model_path else None)
    return None


# --- Cut-out --------------------------------------------------------------------------


def _hesitant(matte: FloatImage) -> bool:
    """True when most of what the cut-out found is a maybe.

    A model in the photo box comes out nearly black and white (a few percent of soft
    edge, a little more for a lattice jib). A photo of something else, a tray full of
    models, say, comes out as a grey haze: staging that would show scraps.
    """
    found = matte > 0.15
    unsure = found & (matte < 0.85)
    return bool(unsure.sum() > MAX_UNSURE_SHARE * max(int(found.sum()), 1))


def _clean_matte(matte: FloatImage) -> FloatImage:
    """Snap near-certain values, drop specks, fill holes inside the model."""
    # Faint values are the photo box's own shadow and haze, not model: cut them off and
    # stretch the rest, which keeps the edge soft but takes the veil away.
    matte = np.clip((np.clip(matte, 0.0, 1.0) - 0.3) / 0.6, 0.0, 1.0).astype(np.float32)
    solid = matte > 0.5
    labels, count = ndimage.label(solid)
    if count > 1:
        sizes = ndimage.sum_labels(solid, labels, index=np.arange(1, count + 1))
        keep = np.zeros(count + 1, dtype=bool)
        keep[1:] = sizes >= sizes.max() * 0.02
        kept = keep[labels]
        # The soft edge around dropped specks goes with them.
        near_kept = ndimage.binary_dilation(kept, iterations=6)
        matte = np.where(near_kept, matte, 0.0).astype(np.float32)
        solid = kept
    holes = ndimage.binary_fill_holes(solid) & ~solid
    # Only small holes are closed: a window the backdrop shows through stays open.
    if holes.any():
        hole_labels, hole_count = ndimage.label(holes)
        hole_sizes = ndimage.sum_labels(holes, hole_labels, index=np.arange(1, hole_count + 1))
        small = np.zeros(hole_count + 1, dtype=bool)
        small[1:] = hole_sizes < solid.sum() * 0.002
        matte = np.where(small[hole_labels], 1.0, matte).astype(np.float32)
    return matte


def _bounding_box(solid: NDArray[np.bool_]) -> Box | None:
    rows = np.flatnonzero(solid.any(axis=1))
    columns = np.flatnonzero(solid.any(axis=0))
    if rows.size == 0 or columns.size == 0:
        return None
    return Box(int(columns[0]), int(rows[0]), int(columns[-1]) + 1, int(rows[-1]) + 1)


def _touched_edges(box: Box, shape: tuple[int, ...]) -> int:
    height, width = shape[:2]
    return sum((box.left <= 1, box.top <= 1, box.right >= width - 1, box.bottom >= height - 1))


def _expanded(box: Box, shape: tuple[int, ...], margin: float) -> Box:
    height, width = shape[:2]
    pad = round(max(box.width, box.height) * margin) + 2
    return Box(
        max(0, box.left - pad),
        max(0, box.top - pad),
        min(width, box.right + pad),
        min(height, box.bottom + pad),
    )


# --- Light ----------------------------------------------------------------------------


def _backdrop_colour(linear: FloatImage, alpha: FloatImage) -> FloatImage:
    """The lit backdrop's colour: the bright part of what is surely not the model.

    The darker part of the backdrop is shadow and vignette; the brightest few pixels may
    be glare. The 80th percentile of the luminance picks the lamp-lit paper.
    """
    far = ~ndimage.binary_dilation(alpha > 0.02, iterations=8)
    pixels = linear[far]
    if pixels.shape[0] < 500:
        pixels = linear.reshape(-1, 3)
    luminance = _luminance(pixels)
    low, high = np.percentile(luminance, [70, 95])
    lit = pixels[(luminance >= low) & (luminance <= high)]
    if lit.shape[0] == 0:
        lit = pixels
    colour: FloatImage = np.median(lit, axis=0).astype(np.float32)
    return colour


def _correct_light(linear: FloatImage, backdrop: FloatImage) -> FloatImage:
    """Neutral, evenly bright backdrop: white balance and exposure from the paper."""
    level = float(_luminance(backdrop[None, :])[0])
    chroma = float((backdrop.max() - backdrop.min()) / max(float(backdrop.max()), 1e-4))
    # A plainly coloured backdrop is no white paper: neutralise only part of it.
    trust = 1.0 if chroma <= NEUTRAL_BACKDROP_CHROMA else 0.35
    gains = np.clip(level / np.maximum(backdrop, 1e-4), 1 / MAX_CHANNEL_GAIN, MAX_CHANNEL_GAIN)
    gains = 1.0 + (gains - 1.0) * trust
    exposure = float(
        np.clip(BACKDROP_LEVEL / max(level, 1e-4), MIN_EXPOSURE_GAIN, MAX_EXPOSURE_GAIN)
    )
    corrected = linear * (gains * exposure).astype(np.float32)
    return _shoulder(corrected)


def _shoulder(linear: FloatImage, knee: float = 0.8) -> FloatImage:
    """Roll highlights off smoothly below 1.0 instead of clipping them flat."""
    over = np.maximum(linear - knee, 0.0)
    head = 1.0 - knee
    rolled = knee + head * (1.0 - np.exp(-over / head))
    return np.where(linear > knee, rolled, linear).astype(np.float32)


def _local_backdrop(linear: FloatImage, alpha: FloatImage) -> FloatImage:
    """The backdrop behind each pixel, spread in from around the model."""
    weight = (1.0 - alpha) ** 2
    sigma = max(4.0, max(alpha.shape) / 120)
    spread = np.stack(
        [ndimage.gaussian_filter(linear[..., c] * weight, sigma) for c in range(3)], axis=-1
    )
    norm = ndimage.gaussian_filter(weight, sigma)[..., None]
    local: FloatImage = (spread / np.maximum(norm, 1e-4)).astype(np.float32)
    return local


def _decontaminate(linear: FloatImage, alpha: FloatImage, backdrop: FloatImage) -> FloatImage:
    """Take the backdrop's light out of the soft edge: F = (I - (1 - a) B) / a."""
    a = alpha[..., None]
    edge = (a > 0.02) & (a < 0.98)
    foreground = (linear - (1.0 - a) * backdrop) / np.maximum(a, 0.02)
    return np.where(edge, np.clip(foreground, 0.0, 1.0), linear).astype(np.float32)


# --- Stage ----------------------------------------------------------------------------


def _stage(cut: Image.Image, subject: Box) -> Image.Image:
    placement = place(subject)
    scale = placement.scale
    width = max(1, round(cut.width * scale))
    height = max(1, round(cut.height * scale))
    scaled = cut.resize((width, height), Image.Resampling.LANCZOS, reducing_gap=3.0)
    if scale < 1.0:
        scaled = scaled.filter(ImageFilter.UnsharpMask(radius=1.2, percent=45, threshold=2))
    origin_x = placement.x - round(subject.left * scale)
    origin_y = placement.y - round(subject.top * scale)

    model = Image.new("RGBA", (CANVAS, CANVAS), (0, 0, 0, 0))
    model.paste(scaled, (origin_x, origin_y))
    shadow = _shadow(model.getchannel("A"), placement.y + placement.height, placement.width)
    stage = Image.new("RGBA", (CANVAS, CANVAS), (*SHADOW_RGB, 0))
    stage.putalpha(shadow)
    return Image.alpha_composite(stage, model)


def _shadow(alpha: Image.Image, standline: int, model_width: int) -> Image.Image:
    """A soft shadow lying flat on the standing line, and a dark seam under the model.

    The floor shadow spans what comes down close to the floor (a crane's jib casts
    none), fading out at both ends. The seam is the model's own outline, moved down a
    little: it shows only as a thin dark line where the model meets the floor.
    """
    mask = np.asarray(alpha, dtype=np.float32) / 255.0
    height = mask.shape[0]
    solid = mask > 0.5
    present = solid.any(axis=0)
    underside = height - 1 - np.argmax(solid[::-1], axis=0)
    reach = round(model_width * 0.12)
    grounded = (present & (underside >= standline - reach)).astype(np.float32)
    bridge = max(3, round(model_width * 0.08)) | 1
    grounded = ndimage.maximum_filter1d(grounded, bridge)
    strength = ndimage.gaussian_filter1d(grounded, max(2.0, model_width * 0.03))
    rows = np.arange(height, dtype=np.float32)[:, None]
    floor_height = max(5.0, model_width * 0.022)
    floor = np.exp(-0.5 * ((rows - standline) / floor_height) ** 2) * strength[None, :]

    offset = max(2, round(model_width * 0.006))
    seam = np.zeros_like(mask)
    seam[offset:] = mask[:-offset]
    # Only near the floor: higher up the outline would read as a second contour.
    seam *= np.clip((rows - (standline - reach)) / max(reach, 1), 0.0, 1.0)
    contact = ndimage.gaussian_filter(seam, max(1.5, model_width * 0.004))
    combined = 1.0 - (1.0 - CONTACT_SHADOW_OPACITY * contact) * (1.0 - FLOOR_SHADOW_OPACITY * floor)
    return Image.fromarray(np.clip(combined * 255.0 + 0.5, 0, 255).astype(np.uint8), "L")


# --- Pixels ---------------------------------------------------------------------------


def _downscaled(image: Image.Image) -> Image.Image:
    if max(image.size) <= WORK_EDGE:
        return image
    copy = image.copy()
    copy.thumbnail((WORK_EDGE, WORK_EDGE), Image.Resampling.LANCZOS, reducing_gap=3.0)
    return copy


def _resized(values: FloatImage, size: tuple[int, int]) -> FloatImage:
    if (values.shape[1], values.shape[0]) == size:
        return values.astype(np.float32)
    channel = Image.fromarray(values.astype(np.float32), "F")
    return np.asarray(channel.resize(size, Image.Resampling.BILINEAR), dtype=np.float32)


def _to_float(image: Image.Image) -> FloatImage:
    return np.asarray(image, dtype=np.float32) / 255.0


def _to_linear(srgb: FloatImage) -> FloatImage:
    return np.where(srgb <= 0.04045, srgb / 12.92, ((srgb + 0.055) / 1.055) ** 2.4).astype(
        np.float32
    )


def _to_srgb(linear: FloatImage) -> FloatImage:
    linear = np.clip(linear, 0.0, 1.0)
    return np.where(
        linear <= 0.0031308, linear * 12.92, 1.055 * np.power(linear, 1 / 2.4) - 0.055
    ).astype(np.float32)


def _luminance(linear: FloatImage) -> FloatImage:
    return (linear @ np.asarray([0.2126, 0.7152, 0.0722], dtype=np.float32)).astype(np.float32)


def _to_image(srgb: FloatImage, alpha: FloatImage) -> Image.Image:
    rgba = np.concatenate([srgb, alpha[..., None]], axis=-1)
    return Image.fromarray(np.clip(rgba * 255.0 + 0.5, 0, 255).astype(np.uint8), "RGBA")
