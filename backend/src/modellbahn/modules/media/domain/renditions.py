"""Which image sizes are rendered, and how large each one comes out.

Pure arithmetic: the infrastructure scales and encodes, this module only decides.
Every size is rendered as WebP and AVIF. Nothing is ever scaled up; an original
smaller than a size simply does not get that size.
"""

from dataclasses import dataclass
from enum import StrEnum
from typing import Final
from uuid import UUID


class RenditionFormat(StrEnum):
    WEBP = "webp"
    AVIF = "avif"

    @property
    def mime_type(self) -> str:
        return f"image/{self.value}"


@dataclass(frozen=True, slots=True)
class RenditionSpec:
    """A size of the catalogue: ``height`` set means cropped to exactly that box."""

    name: str
    width: int
    height: int | None = None

    @property
    def cropped(self) -> bool:
        return self.height is not None


THUMB: Final = RenditionSpec("thumb", 256, 256)
WIDTH_STEPS: Final = (
    RenditionSpec("sm", 480),
    RenditionSpec("md", 960),
    RenditionSpec("lg", 1600),
    RenditionSpec("xl", 2400),
)
# Preview image for links shared in messengers and social networks.
OPEN_GRAPH: Final = RenditionSpec("og", 1200, 630)
RENDITION_SPECS: Final = (THUMB, *WIDTH_STEPS, OPEN_GRAPH)
RENDITION_NAMES: Final = frozenset(spec.name for spec in RENDITION_SPECS)
RENDITION_FORMATS: Final = tuple(RenditionFormat)

# The square thumbnail needs this much on the shorter side.
MIN_EDGE: Final = THUMB.width


@dataclass(frozen=True, slots=True)
class PlannedRendition:
    """One size to render from a given original."""

    name: str
    width: int
    height: int
    cropped: bool


def plan_renditions(width: int, height: int) -> list[PlannedRendition]:
    """The sizes to render from an original of ``width`` x ``height`` pixels.

    * ``thumb``: 256 x 256, cut from the middle.
    * ``sm`` to ``xl``: the original's aspect ratio, each only up to the original
      width. An original narrower than ``sm`` gets ``sm`` at its own width, so every
      image has at least one uncropped size.
    * ``og``: 1200 x 630, cut from the middle, only if the original covers that box.

    The caller has checked :data:`MIN_EDGE`.
    """
    if min(width, height) < MIN_EDGE:
        msg = f"an original needs at least {MIN_EDGE} px on its shorter side"
        raise ValueError(msg)
    planned = [PlannedRendition(THUMB.name, THUMB.width, THUMB.width, cropped=True)]
    steps = [spec for spec in WIDTH_STEPS if spec.width <= width]
    if steps:
        planned.extend(
            PlannedRendition(
                spec.name, spec.width, _scaled_height(width, height, spec.width), False
            )
            for spec in steps
        )
    else:
        planned.append(PlannedRendition(WIDTH_STEPS[0].name, width, height, cropped=False))
    og_height = OPEN_GRAPH.height or 0
    if width >= OPEN_GRAPH.width and height >= og_height:
        planned.append(PlannedRendition(OPEN_GRAPH.name, OPEN_GRAPH.width, og_height, cropped=True))
    return planned


def _scaled_height(width: int, height: int, target_width: int) -> int:
    return max(1, round(height * target_width / width))


def storage_key(
    asset_id: UUID, name: str, content_hash: str, rendition_format: RenditionFormat
) -> str:
    """Public storage key of a rendered size: ``{asset}/{name}-{hash8}.{format}``.

    The content hash in the name makes every key immutable: a reprocessed image gets
    new names, so no cache ever serves an outdated version.
    """
    return f"{asset_id}/{name}-{content_hash[:8]}.{rendition_format.value}"
