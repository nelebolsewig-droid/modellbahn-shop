"""What a scanned or typed code names: a unit, a location, a variant, a part, or nothing.

The labels carry URLs (``https://shop.example/u/7KQ2X9F4MZ``), so that an ordinary phone
camera opens the right page; a hand scanner delivers the same text. People type codes
with spaces, hyphens or lower case. :func:`interpretations` turns all of that into the
readings worth looking up, most likely first. It needs no database and no network, so
the frontend's scanner applies the same rules before it sends anything.
"""

from dataclasses import dataclass
from enum import StrEnum
from urllib.parse import urlsplit

from modellbahn.modules.inventory.domain.codes import (
    LOCATION_CODE,
    is_valid_ean13,
    is_valid_unit_code,
    normalize_unit_code,
)
from modellbahn.modules.manufacturing.contracts.part_numbers import is_part_number

MAX_RAW_LENGTH = 300


class CodeKind(StrEnum):
    UNIT = "unit"
    LOCATION = "location"
    VARIANT = "variant"
    PART = "part"


@dataclass(frozen=True, slots=True)
class Reading:
    """One interpretation of a scan: the kind of thing and its normalised code."""

    kind: CodeKind
    code: str


def _from_url(raw: str) -> list[Reading] | None:
    parts = urlsplit(raw)
    if not (parts.scheme and parts.netloc) and not raw.startswith("/"):
        return None
    segments = [segment for segment in parts.path.split("/") if segment]
    if len(segments) < 2:  # noqa: PLR2004
        return []
    marker, code = segments[-2], segments[-1]
    if marker == "u":
        unit = normalize_unit_code(code)
        return [Reading(CodeKind.UNIT, unit)] if is_valid_unit_code(unit) else []
    if marker == "l":
        location = code.upper()
        return [Reading(CodeKind.LOCATION, location)] if LOCATION_CODE.fullmatch(location) else []
    return []


def interpretations(raw: str) -> list[Reading]:
    """The readings of ``raw`` worth looking up, most likely first; empty if none fits.

    A typed ``R001-F004-B1`` could in theory also be a unit code with a valid check
    character; both readings are returned, and the caller takes the one that exists.
    A part number (``STW-ALT-DACH-H0``, on the label of a box of parts) looks like a
    location code as well; it comes last, after every location.
    """
    text = raw.strip()
    if not text or len(text) > MAX_RAW_LENGTH:
        return []
    from_url = _from_url(text)
    if from_url is not None:
        return from_url
    if is_valid_ean13(text):
        return [Reading(CodeKind.VARIANT, text)]
    readings: list[Reading] = []
    unit = normalize_unit_code(text)
    if is_valid_unit_code(unit):
        readings.append(Reading(CodeKind.UNIT, unit))
    location = text.upper()
    if LOCATION_CODE.fullmatch(location):
        # A code with hyphens is first of all a location; only grouped like 7KQ2-X9F4-MZ
        # is it more likely a unit.
        is_grouped_unit = [len(part) for part in location.split("-")] == [4, 4, 2]
        reading = Reading(CodeKind.LOCATION, location)
        if "-" in location and not is_grouped_unit:
            readings.insert(0, reading)
        else:
            readings.append(reading)
    if is_part_number(location):
        readings.append(Reading(CodeKind.PART, location))
    return readings
