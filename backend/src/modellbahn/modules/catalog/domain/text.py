"""Rules for the texts and addresses of the catalogue: names, descriptions, slugs."""

import re
import unicodedata
from typing import Final

from modellbahn.modules.catalog.domain.errors import InvalidFieldError

SLUG_MAX_LENGTH: Final = 80
_SLUG: Final = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
# German letters that have a customary spelling without diacritics.
_TRANSLITERATION: Final = str.maketrans(
    {"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss", "Ä": "ae", "Ö": "oe", "Ü": "ue", "ẞ": "ss"}
)
_BIDI_CONTROLS: Final = frozenset("\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069")


def _without_controls(value: str, *, keep: str = "") -> str:
    return "".join(
        char
        for char in value
        if char in keep
        or (unicodedata.category(char) not in {"Cc", "Cf"} and char not in _BIDI_CONTROLS)
    )


def single_line(value: str, *, field: str, max_length: int, required: bool = True) -> str:
    """A name or short text: one line, whitespace collapsed, no control characters."""
    text = " ".join(_without_controls(unicodedata.normalize("NFC", value)).split())
    if required and not text:
        raise InvalidFieldError(field, "required", "must not be empty")
    if len(text) > max_length:
        raise InvalidFieldError(field, "too_long", f"at most {max_length} characters")
    return text


def multi_line(value: str, *, field: str, max_length: int) -> str:
    """A description: line breaks kept, trailing spaces and control characters removed."""
    text = _without_controls(unicodedata.normalize("NFC", value), keep="\n")
    lines = [line.rstrip() for line in text.replace("\r\n", "\n").split("\n")]
    text = "\n".join(lines).strip("\n")
    # More than one empty line in a row carries no meaning.
    text = re.sub(r"\n{3,}", "\n\n", text)
    if len(text) > max_length:
        raise InvalidFieldError(field, "too_long", f"at most {max_length} characters")
    return text


def slugify(value: str) -> str:
    """The address part for a name: "Stellwerk Altenau (H0)" -> "stellwerk-altenau-h0"."""
    text = unicodedata.normalize("NFKD", value.translate(_TRANSLITERATION))
    text = text.encode("ascii", "ignore").decode("ascii").lower()
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    text = text[:SLUG_MAX_LENGTH].rstrip("-")
    if not text:
        raise InvalidFieldError("slug", "invalid", "the name yields no usable address")
    return text


def check_slug(value: str, *, field: str = "slug") -> str:
    """An address chosen by hand: lower-case letters, digits and single hyphens."""
    if len(value) > SLUG_MAX_LENGTH:
        raise InvalidFieldError(field, "too_long", f"at most {SLUG_MAX_LENGTH} characters")
    if not _SLUG.fullmatch(value):
        raise InvalidFieldError(field, "invalid", "only a-z, 0-9 and single hyphens")
    return value
