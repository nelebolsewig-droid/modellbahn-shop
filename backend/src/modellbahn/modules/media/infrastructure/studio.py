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

import gc
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, Protocol

import numpy as np
import structlog
from numpy.typing import NDArray
from PIL import Image, ImageDraw, ImageFilter
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
# Black parts in the model's own black shadow (tyres under a car): what is this dark
# against the backdrop and hangs on the model belongs to it. Fully from DARK_SURE
# down, not at all above DARK_MAYBE (shares of the backdrop's brightness), and only
# this far from what the cut-out found (in model sizes).
DARK_SURE: Final = 0.035
DARK_MAYBE: Final = 0.12
DARK_REACH: Final = 0.12
# Only in front of a light backdrop, and never more than this share of the model:
# anything else is not a tyre in a photo box but a dark room.
DARK_MIN_BACKDROP: Final = 0.2
DARK_MAX_SHARE: Final = 0.25
# Espresso #26211e, the ink of the shop, as shadow colour.
SHADOW_RGB: Final = (0x26, 0x21, 0x1E)
# The photo's own shadow: how far around the model it counts (in model sizes), below
# which darkening it is noise, how it is strengthened and where it is capped.
SHADOW_REACH: Final = 0.18
# The floor begins around here, as a share of the model's height from its top.
SHADOW_FLOOR_TOP: Final = 0.3
SHADOW_FLOOR_FULL: Final = 0.65
SHADOW_FLOOR: Final = 0.07
MIN_FAR_PIXELS: Final = 20
SHADOW_GAIN: Final = 0.7
SHADOW_MAX: Final = 0.5
# Below this the photo has no shadow worth keeping, and a plain soft one is drawn.
FAINT_SHADOW: Final = 0.12
MIN_SHADOW_AREA: Final = 0.03
# The drawn shadow for pictures without one of their own (renders): it lies only where
# the model stands. Fractions of the model size unless said otherwise.
# The parts this close above the floor are laid flat onto it, like light from above.
FLAT_REACH: Final = 0.16
FLAT_SQUASH: Final = 0.2
FLAT_DROP: Final = 0.006
FLAT_SLANT: Final = 0.02
FLAT_WEIGHT: Final = 0.8
# The floor between the feet (wheels) of every part in the lowest share of the model's
# height, so a vehicle seen from the side or at an angle stands on all of them.
FEET_ZONE: Final = 0.3
FEET_REACH: Final = 0.02
FEET_GROW: Final = 0.01
NEAR_BLUR: Final = 0.013
NEAR_OPACITY: Final = 0.42
WIDE_BLUR: Final = 0.038
WIDE_OPACITY: Final = 0.32
CONTACT_BLUR: Final = 0.0035
CONTACT_OPACITY: Final = 1.3
SOFT_SHADOW_MAX: Final = 0.75


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
        linear = _to_linear(rgb)
        alpha = _with_dark_parts(_clean_matte(matte), _luminance(linear))
        solid = alpha > 0.5
        subject = _bounding_box(solid)
        total = solid.size
        if subject is None or not trustworthy(
            int(solid.sum()), total, _touched_edges(subject, solid.shape)
        ):
            return StudioResult(None, "no model found against the backdrop")

        backdrop = _backdrop_colour(linear, alpha)
        corrected = _correct_light(linear, backdrop)
        local_backdrop = _local_backdrop(corrected, alpha)

        # The soft rim reaches further than the solid model; none of it may be cut off.
        crop = _expanded(_bounding_box(alpha > 0.01) or subject, solid.shape, CROP_MARGIN)
        window = (slice(crop.top, crop.bottom), slice(crop.left, crop.right))
        fg = _decontaminate(corrected[window], alpha[window], local_backdrop[window])
        cut = _to_image(_to_srgb(fg), alpha[window])

        inner = Box(
            subject.left - crop.left,
            subject.top - crop.top,
            subject.right - crop.left,
            subject.bottom - crop.top,
        )
        # The photo's own shadow, with room around the model for it to run out in.
        reach = round(max(subject.width, subject.height) * SHADOW_REACH) + 1
        wide = Box(
            max(0, subject.left - reach),
            max(0, subject.top - reach),
            min(solid.shape[1], subject.right + reach),
            min(solid.shape[0], subject.bottom + reach),
        )
        shadow = _own_shadow(corrected, alpha, subject)[
            wide.top : wide.bottom, wide.left : wide.right
        ]
        offset = (wide.left - crop.left, wide.top - crop.top)
        return StudioResult(_stage(cut, inner, shadow, offset))


class IsnetSegmenter:
    """Neural cut-out with ISNet (``isnet-general-use``) on onnxruntime.

    The model is loaded for each photo and let go afterwards. Loading costs a second
    or two; keeping it would hold several hundred megabytes for good on a server that
    cuts out a photo now and then, not all day.
    """

    INPUT_EDGE: Final = 1024
    MEAN: Final = (0.485, 0.456, 0.406)

    def __init__(self, model_path: Path, *, threads: int = 2) -> None:
        self._model_path = model_path
        self._threads = threads
        self._run_lock = threading.Lock()

    def _open(self) -> Any:
        import onnxruntime  # noqa: PLC0415  # heavy, only needed by the worker

        options = onnxruntime.SessionOptions()
        options.intra_op_num_threads = self._threads
        options.inter_op_num_threads = 1
        # No arena: memory goes back to the system when the photo is done.
        options.enable_cpu_mem_arena = False
        return onnxruntime.InferenceSession(
            str(self._model_path), options, providers=["CPUExecutionProvider"]
        )

    def matte(self, image: Image.Image) -> FloatImage:
        edge = self.INPUT_EDGE
        resized = image.convert("RGB").resize((edge, edge), Image.Resampling.BILINEAR)
        pixels = np.asarray(resized, dtype=np.float32)
        pixels = pixels / max(float(pixels.max()), 1e-6)
        pixels = pixels - np.asarray(self.MEAN, dtype=np.float32)
        tensor = pixels.transpose(2, 0, 1)[None, ...]
        # One photo at a time: a run takes over a gigabyte, several at once would add up.
        with self._run_lock:
            session = self._open()
            try:
                input_name = session.get_inputs()[0].name
                prediction = np.array(session.run(None, {input_name: tensor})[0], dtype=np.float32)
            finally:
                del session
                gc.collect()
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


def _with_dark_parts(alpha: FloatImage, luminance: FloatImage) -> FloatImage:
    """Add what is nearly black and hangs on the model: tyres in the shadow under a car.

    The cut-out cannot tell a black tyre from the black shadow it stands in and drops
    both, which leaves a car without wheels. Nothing in the photo tells them apart, so
    the darkest core goes with the model, as the photo shows it; the lighter shadow
    around it is still taken as shadow.
    """
    solid = alpha > 0.5
    free = alpha < 0.02
    subject = _bounding_box(solid)
    if subject is None or not free.any():
        return alpha
    backdrop = float(np.median(luminance[free]))
    if backdrop < DARK_MIN_BACKDROP:
        return alpha
    dark = _smooth((DARK_MAYBE - luminance / backdrop) / (DARK_MAYBE - DARK_SURE))
    reach = max(subject.width, subject.height) * DARK_REACH
    distance = ndimage.distance_transform_edt(~solid)
    near = distance <= reach
    candidate = (luminance < DARK_SURE * 2 * backdrop) & near & ~solid
    labels, count = ndimage.label(candidate)
    if count == 0:
        return alpha
    touching = np.unique(labels[ndimage.binary_dilation(solid, iterations=2) & candidate])
    keep = np.zeros(count + 1, dtype=bool)
    keep[touching] = True
    keep[0] = False
    if int(keep[labels].sum()) > DARK_MAX_SHARE * int(solid.sum()):
        return alpha
    # Around it the black thins out into shadow: let it fade instead of ending in a cut.
    around = ndimage.binary_dilation(keep[labels], iterations=max(3, round(reach * 0.3)))
    fade = _smooth((reach - distance) / (reach * 0.5))
    added: FloatImage = np.maximum(alpha, np.where(around, dark * fade, 0.0)).astype(np.float32)
    return added


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


def _stage(
    cut: Image.Image, subject: Box, shadow: FloatImage, shadow_offset: tuple[int, int]
) -> Image.Image:
    """The model on the square stage, on its shadow. ``shadow_offset`` is where the
    shadow map's corner lies relative to ``cut``'s (negative: it reaches further out)."""
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

    size = max(placement.width, placement.height)
    own = Image.fromarray(np.clip(shadow * 255.0 + 0.5, 0, 255).astype(np.uint8), "L")
    own = own.resize(
        (max(1, round(own.width * scale)), max(1, round(own.height * scale))),
        Image.Resampling.BILINEAR,
    )
    floor = Image.new("L", (CANVAS, CANVAS), 0)
    floor.paste(
        own,
        (origin_x + round(shadow_offset[0] * scale), origin_y + round(shadow_offset[1] * scale)),
    )
    cast = np.asarray(floor, dtype=np.float32) / 255.0
    if float((cast > FAINT_SHADOW).sum()) < MIN_SHADOW_AREA * placement.width * placement.height:
        # A photo without a shadow of its own (an edited one on plain white, say).
        cast = _soft_shadow(model.getchannel("A"), placement.y + placement.height, size)
    cast = cast * _canvas_fade()
    stage = Image.new("RGBA", (CANVAS, CANVAS), (*SHADOW_RGB, 0))
    stage.putalpha(Image.fromarray(np.clip(cast * 255.0 + 0.5, 0, 255).astype(np.uint8), "L"))
    return Image.alpha_composite(stage, model)


def _canvas_fade() -> FloatImage:
    """1 inside, running out to 0 at the canvas edge: no shadow ends in a cut."""
    ramp = np.clip(np.minimum(np.arange(CANVAS), np.arange(CANVAS)[::-1]) / (CANVAS * 0.05), 0, 1)
    fade: FloatImage = np.minimum.outer(ramp, ramp).astype(np.float32)
    return fade


def _own_shadow(linear: FloatImage, alpha: FloatImage, subject: Box) -> FloatImage:
    """The shadow the model really casts in the photo, as opacity per pixel.

    The backdrop without shadow is a smooth surface, fitted to what is not model and
    not darker than its surroundings. Where the photo is darker than that surface, the
    model shades the floor: under it deeply, beside it softly. Only near the model;
    further out a darker backdrop is vignette or dirt.
    """
    luminance = np.maximum(_luminance(linear), 1e-4)
    height, width = luminance.shape
    step = max(1, max(height, width) // 400)
    small = np.log(luminance[::step, ::step])
    free = alpha[::step, ::step] < 0.02
    ys, xs = np.mgrid[0 : small.shape[0], 0 : small.shape[1]].astype(np.float32)
    x, y = xs / small.shape[1], ys / small.shape[0]
    basis = np.stack([np.ones_like(x), x, y, x * x, x * y, y * y], axis=-1)
    keep = free
    surface = small
    for _ in range(4):
        if int(keep.sum()) < 50:
            return np.zeros_like(luminance)
        coefficients, *_rest = np.linalg.lstsq(basis[keep], small[keep], rcond=None)
        surface = basis @ coefficients
        # Shadows only ever darken: drop what lies below the surface and fit again.
        keep = free & (small > surface - 0.03)
    lit = np.exp(_resized(surface.astype(np.float32), (width, height)))
    shade = np.clip(1.0 - luminance / lit, 0.0, 1.0)
    shade = ndimage.gaussian_filter(shade, max(1.5, max(height, width) / 900))
    shade = np.clip((shade - SHADOW_FLOOR) / (1.0 - SHADOW_FLOOR), 0.0, 1.0)

    solid = alpha > 0.5
    size = max(subject.width, subject.height, 1)
    distance = ndimage.distance_transform_edt(~solid)
    shade = np.clip(shade - _row_haze(shade, (alpha < 0.02) & (distance > size * 0.25)), 0.0, 1.0)
    # Only near the model, running out smoothly ...
    near = _smooth(1.0 - distance / (size * SHADOW_REACH))
    # ... only on the floor, which lies around the lower part of the model ...
    rows = (np.arange(height, dtype=np.float32) - subject.top) / max(subject.height, 1)
    floor = _smooth((rows - SHADOW_FLOOR_TOP) / (SHADOW_FLOOR_FULL - SHADOW_FLOOR_TOP))[:, None]
    # ... and never ending in a cut where the photo ends.
    border = size * 0.08
    to_edge_y = np.minimum(np.arange(height), np.arange(height)[::-1])[:, None] / border
    to_edge_x = np.minimum(np.arange(width), np.arange(width)[::-1])[None, :] / border
    inside = _smooth(np.minimum(to_edge_y, to_edge_x))
    own: FloatImage = (
        np.minimum(shade * SHADOW_GAIN, SHADOW_MAX) * near * floor * inside * (1.0 - alpha)
    ).astype(np.float32)
    return own


def _row_haze(shade: FloatImage, far: NDArray[np.bool_]) -> FloatImage:
    """How dark each row is away from the model: a wall behind it, a fold in the
    backdrop. That is no shadow of the model's and is taken off the whole row."""
    counted = far.sum(axis=1)
    known = counted >= MIN_FAR_PIXELS
    if not known.any():
        return np.zeros((shade.shape[0], 1), dtype=np.float32)
    level = np.where(far, shade, np.nan)[known]
    haze = np.nanmedian(level, axis=1)
    rows = np.arange(shade.shape[0])
    filled = np.interp(rows, rows[known], haze)
    smoothed: FloatImage = ndimage.gaussian_filter1d(filled, 2.0).astype(np.float32)[:, None]
    return smoothed


def _smooth(values: NDArray[np.floating]) -> FloatImage:
    """Smoothstep: 0 below 0, 1 above 1, without a kink in between."""
    t = np.clip(values, 0.0, 1.0)
    smooth: FloatImage = (t * t * (3.0 - 2.0 * t)).astype(np.float32)
    return smooth


def _soft_shadow(alpha: Image.Image, standline: int, model_size: int) -> FloatImage:
    """A soft shadow for pictures that bring none of their own, such as renders.

    Two parts make it look photographed: the floor between the feet of each part
    (wheels, a bucket, a stand) and the parts close above the floor, laid flat onto it.
    Nothing is drawn under parts in the air, so no grey bar under a crane's boom.
    """
    del standline  # the model's own feet say where the floor is
    mask = np.asarray(alpha, dtype=np.float32) / 255.0
    solid = mask > 0.5
    rows = np.flatnonzero(solid.any(axis=1))
    if rows.size == 0:
        return np.zeros_like(mask)
    feet, contact = _feet_floor(solid, rows, model_size)
    flat = _flat_parts(solid, rows, model_size)
    floor = _blurred(feet, model_size)
    laid = _blurred(flat, model_size) * FLAT_WEIGHT
    cast = np.maximum(floor, laid) + 0.3 * np.minimum(floor, laid)
    touch = ndimage.gaussian_filter(contact, model_size * CONTACT_BLUR) * CONTACT_OPACITY
    soft: FloatImage = np.clip(cast + touch, 0.0, SOFT_SHADOW_MAX).astype(np.float32)
    return soft


def _blurred(source: FloatImage, model_size: int) -> FloatImage:
    near = ndimage.gaussian_filter(source, model_size * NEAR_BLUR) * NEAR_OPACITY
    wide = ndimage.gaussian_filter(source, model_size * WIDE_BLUR) * WIDE_OPACITY
    blurred: FloatImage = (near + wide).astype(np.float32)
    return blurred


def _feet_floor(
    solid: NDArray[np.bool_], rows: NDArray[np.intp], model_size: int
) -> tuple[FloatImage, FloatImage]:
    """The floor between the feet of each low part, and where those feet touch it."""
    height, width = solid.shape
    low = solid.copy()
    low[: int(rows[-1] - (rows[-1] - rows[0]) * FEET_ZONE)] = False
    labels, count = ndimage.label(low)
    reach = max(2, round(FEET_REACH * model_size))
    floor = Image.new("L", (width, height), 0)
    draw = ImageDraw.Draw(floor)
    contact = np.zeros((height, width), dtype=np.float32)
    for label in range(1, count + 1):
        part = labels == label
        if part.sum() < (model_size * 0.01) ** 2:
            continue
        columns = np.flatnonzero(part.any(axis=0))
        underside = np.full(width, -1)
        underside[columns] = height - 1 - np.argmax(part[::-1, columns], axis=0)
        lowest = ndimage.maximum_filter1d(underside, 2 * reach + 1)
        feet = [(int(x), int(underside[x])) for x in columns if underside[x] >= lowest[x] - 1]
        outline = _convex_hull(feet)
        if len(outline) >= 3:
            draw.polygon(outline, fill=255)
        else:
            draw.line(outline, fill=255, width=3)
        for x, y in feet:
            contact[max(0, y - 1) : y + 2, x] = 1.0
    grown = np.asarray(floor, dtype=np.float32) / 255.0
    size = (max(1, round(FEET_GROW * model_size * 0.4)), max(1, round(FEET_GROW * model_size)))
    return ndimage.grey_dilation(grown, size=size).astype(np.float32), contact


def _flat_parts(solid: NDArray[np.bool_], rows: NDArray[np.intp], model_size: int) -> FloatImage:
    """The parts close above the floor line, laid flat onto the floor behind them."""
    height, width = solid.shape
    underside = height - 1 - np.argmax(solid[::-1], axis=0)
    present = np.flatnonzero(solid.any(axis=0))
    low = present[underside[present] >= rows[-1] - (rows[-1] - rows[0]) * 0.25]
    hull = _lower_hull(low, underside[low])
    floor_line = np.interp(np.arange(width), hull[:, 0], hull[:, 1]).astype(np.float32)
    reach = FLAT_REACH * model_size
    above = floor_line[None, :] - np.arange(height, dtype=np.float32)[:, None]
    span = (np.arange(width) >= hull[0, 0]) & (np.arange(width) <= hull[-1, 0])
    close = solid & (above <= reach) & (above >= -2) & span[None, :]
    ys, xs = np.nonzero(close)
    lift = above[ys, xs]
    to_y = np.round(floor_line[xs] - lift * FLAT_SQUASH + FLAT_DROP * model_size).astype(int)
    to_x = np.round(xs + FLAT_SLANT * model_size * (1 - lift / reach)).astype(int)
    keep = (to_y >= 0) & (to_y < height) & (to_x >= 0) & (to_x < width)
    flat = np.zeros((height, width), dtype=np.float32)
    flat[to_y[keep], to_x[keep]] = 1.0
    closed: FloatImage = ndimage.grey_closing(flat, size=(3, 3)).astype(np.float32)
    return closed


def _convex_hull(points: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """The convex outline of the points (monotone chain); fewer than three stay as they are."""
    ordered = sorted(set(points))
    if len(ordered) < 3:
        return ordered

    def half(chain: list[tuple[int, int]]) -> list[tuple[int, int]]:
        out: list[tuple[int, int]] = []
        for p in chain:
            while (
                len(out) >= 2
                and (
                    (out[-1][0] - out[-2][0]) * (p[1] - out[-2][1])
                    - (out[-1][1] - out[-2][1]) * (p[0] - out[-2][0])
                )
                <= 0
            ):
                out.pop()
            out.append(p)
        return out

    return half(ordered)[:-1] + half(ordered[::-1])[:-1]


def _lower_hull(xs: NDArray[np.intp], ys: NDArray[np.intp]) -> NDArray[np.float32]:
    """The lower convex hull of the points, left to right (image rows grow downwards)."""
    hull: list[tuple[float, float]] = []
    for x, y in zip(xs.tolist(), ys.tolist(), strict=True):
        while len(hull) >= 2:
            (x1, y1), (x2, y2) = hull[-2], hull[-1]
            # Keep the last point only if it lies below the line to the new one.
            if (x2 - x1) * (y - y1) - (y2 - y1) * (x - x1) >= 0:
                hull.pop()
            else:
                break
        hull.append((float(x), float(y)))
    return np.asarray(hull, dtype=np.float32)


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
