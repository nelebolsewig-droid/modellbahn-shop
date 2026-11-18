"""The photo studio: where a cut-out model stands in the finished product photo.

Pure arithmetic, like :mod:`renditions`: the infrastructure cuts out, corrects and
draws, this module only decides the frame. Every studio photo is a square of the same
size in which the model stands on the same line, fills the same box and is centred
the same way. Side by side in the shop, the models stand in a row (ADR 0031).
"""

from dataclasses import dataclass
from typing import Final

# Edge length of the finished photo. Large enough for the xl size (2400 px is rendered
# only from wider originals, so 2048 gives xl a miss and lg the full width).
CANVAS: Final = 2048
# The box the model may fill: wide models touch the sides, tall ones the top line.
BOX_WIDTH: Final = 0.84
BOX_HEIGHT: Final = 0.64
# The standing line: the lowest point of every model, measured from the top.
STANDLINE: Final = 0.80
# Room around the cut-out kept when cropping, so the soft edge is not cut off.
CROP_MARGIN: Final = 0.02
# A cut-out smaller than this share of the photo, or larger, is not trusted.
MIN_SUBJECT_SHARE: Final = 0.003
MAX_SUBJECT_SHARE: Final = 0.85
# A model may run off two sides of the photo (a corner), not off three.
MAX_TOUCHED_EDGES: Final = 2


@dataclass(frozen=True, slots=True)
class Box:
    """A rectangle in pixels; ``right`` and ``bottom`` are exclusive."""

    left: int
    top: int
    right: int
    bottom: int

    @property
    def width(self) -> int:
        return self.right - self.left

    @property
    def height(self) -> int:
        return self.bottom - self.top


@dataclass(frozen=True, slots=True)
class Placement:
    """Where the cropped model goes: scaled by ``scale``, its top-left corner at ``x, y``."""

    scale: float
    x: int
    y: int
    width: int
    height: int


def place(subject: Box, canvas: int = CANVAS) -> Placement:
    """Scale ``subject`` into the box and stand it on the line, centred horizontally."""
    if subject.width <= 0 or subject.height <= 0:
        msg = "the subject box is empty"
        raise ValueError(msg)
    scale = min(canvas * BOX_WIDTH / subject.width, canvas * BOX_HEIGHT / subject.height)
    width = max(1, round(subject.width * scale))
    height = max(1, round(subject.height * scale))
    x = round((canvas - width) / 2)
    y = round(canvas * STANDLINE) - height
    return Placement(scale=scale, x=x, y=y, width=width, height=height)


def trustworthy(subject_pixels: int, total_pixels: int, touched_edges: int) -> bool:
    """Whether a cut-out looks like a model in a photo box.

    Too little (nothing found) or too much (the backdrop counted as model), or a cut-out
    that runs off three sides of the photo, is better left alone than put on stage.
    """
    if total_pixels <= 0:
        return False
    share = subject_pixels / total_pixels
    return MIN_SUBJECT_SHARE <= share <= MAX_SUBJECT_SHARE and touched_edges <= MAX_TOUCHED_EDGES
