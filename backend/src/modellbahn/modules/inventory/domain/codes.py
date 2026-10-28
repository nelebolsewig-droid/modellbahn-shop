"""The codes on the labels: units, locations, and the EAN-13 of variants.

*Unit codes* are ten characters of Crockford's Base32: nine random ones and a check
character. The alphabet has no I, L, O or U, so nothing can be mistaken for something
else, and reading tolerates the usual slips (``O`` for ``0``, ``I`` or ``L`` for ``1``).
The check character follows the Luhn mod N algorithm over the same alphabet: every
single wrong character and almost every swap of two neighbours is caught, and it is
itself a Base32 character, so the code stays URL-safe.

*Location codes* join the segments below the site with hyphens: ``R02-F04-B12`` is box
12 in compartment 4 of shelf 2.
"""

import re
import secrets
from typing import Final

ALPHABET: Final = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
UNIT_CODE_LENGTH: Final = 10
UNIT_CODE: Final = re.compile(rf"[{ALPHABET}]{{{UNIT_CODE_LENGTH}}}")
# Readings of characters the alphabet leaves out.
_READ_AS: Final = str.maketrans({"O": "0", "I": "1", "L": "1"})
_SEPARATORS: Final = re.compile(r"[\s-]+")

SEGMENT: Final = re.compile(r"[A-Z0-9]{1,8}")
LOCATION_CODE: Final = re.compile(r"[A-Z0-9]{1,8}(?:-[A-Z0-9]{1,8}){0,4}")
EAN13: Final = re.compile(r"[0-9]{13}")


def _luhn_sum(code: str, *, start_factor: int) -> int:
    base = len(ALPHABET)
    factor = start_factor
    total = 0
    for char in reversed(code):
        addend = factor * ALPHABET.index(char)
        factor = 3 - factor  # 2, 1, 2, 1, ...
        total += addend // base + addend % base
    return total


def check_character(body: str) -> str:
    """The Luhn mod 32 check character for ``body`` (characters of :data:`ALPHABET`)."""
    remainder = _luhn_sum(body, start_factor=2) % len(ALPHABET)
    return ALPHABET[(len(ALPHABET) - remainder) % len(ALPHABET)]


def is_valid_unit_code(code: str) -> bool:
    """Ten characters of the alphabet whose last one checks the other nine."""
    return bool(UNIT_CODE.fullmatch(code)) and _luhn_sum(code, start_factor=1) % 32 == 0


def new_unit_code() -> str:
    """Nine random characters (32⁹ ≈ 35 trillion possibilities) and the check character."""
    body = "".join(secrets.choice(ALPHABET) for _ in range(UNIT_CODE_LENGTH - 1))
    return body + check_character(body)


def normalize_unit_code(text: str) -> str:
    """Upper case, without spaces and hyphens, with O read as 0 and I or L as 1."""
    return _SEPARATORS.sub("", text).upper().translate(_READ_AS)


def format_unit_code(code: str) -> str:
    """``7KQ2X9F4MZ`` as people read it aloud: ``7KQ2 X9F4 MZ``."""
    return f"{code[:4]} {code[4:8]} {code[8:]}"


def is_valid_ean13(digits: str) -> bool:
    """Thirteen digits whose last one is the GS1 check digit of the others."""
    if not EAN13.fullmatch(digits):
        return False
    total = sum(int(digit) * (3 if index % 2 else 1) for index, digit in enumerate(digits[:12]))
    return (10 - total % 10) % 10 == int(digits[12])
