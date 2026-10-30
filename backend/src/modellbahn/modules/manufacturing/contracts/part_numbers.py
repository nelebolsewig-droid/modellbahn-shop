"""The format of part numbers, for the scanner of the stock (a part's label carries it).

Plain Python like the domain it comes from: importing it keeps a domain layer pure.
"""

from modellbahn.modules.manufacturing.domain.model import PART_NUMBER, PART_NUMBER_MAX_LENGTH

__all__ = ["PART_NUMBER_MAX_LENGTH", "is_part_number"]


def is_part_number(text: str) -> bool:
    """True if ``text`` (upper case) could be a part number such as ``STW-ALT-DACH-H0``."""
    return len(text) <= PART_NUMBER_MAX_LENGTH and bool(PART_NUMBER.fullmatch(text))
