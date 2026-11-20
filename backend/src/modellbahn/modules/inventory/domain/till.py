"""The till (*Kasse*): sales rung up in the SumUp app book pieces out by themselves (ADR 0041).

SumUp names what was sold only by the name typed into its app; it knows nothing of our
variants. Each name is assigned to a variant once (*Kassenartikel*), and every later sale
under that name books the oldest free piece of it out as sold. A price typed in without
an article (*Individueller Betrag*) names nothing and stays for someone to book by hand.
"""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Final
from uuid import UUID

from modellbahn.modules.inventory.domain.errors import InvalidFieldError

TILL_NAME_MAX_LENGTH: Final = 200
TILL_QUANTITY_MAX: Final = 999

CUSTOM_AMOUNT_NAMES: Final = frozenset({"", "individueller betrag", "custom amount", "betrag"})
"""What the SumUp app calls a price typed in without an article, in the languages it speaks."""


def till_key(name: str) -> str:
    """The name as it is matched: case and spacing do not count (``„EDK 6  tt“`` = ``edk 6 tt``)."""
    return " ".join(name.split()).casefold()


def is_custom_amount(name: str) -> bool:
    return till_key(name) in CUSTOM_AMOUNT_NAMES


class TillPayment(StrEnum):
    CARD = "card"
    CASH = "cash"


class TillLineState(StrEnum):
    """Where a line of a till sale stands."""

    BOOKED = "booked"
    """All its pieces were booked out as sold."""
    UNASSIGNED = "unassigned"
    """Its name is not yet assigned to a variant: it waits for someone to assign it."""
    CUSTOM = "custom"
    """A price typed in without an article: someone books the piece out by hand."""
    SHORT = "short"
    """Assigned, but fewer free pieces than sold: the rest is booked when they come in."""
    IGNORED = "ignored"
    """Its name is no model (postage, lettering): nothing to book."""
    DONE = "done"
    """Taken care of by hand."""


OPEN_STATES: Final = frozenset(
    {TillLineState.UNASSIGNED, TillLineState.CUSTOM, TillLineState.SHORT}
)
"""Lines somebody still has to look at."""


@dataclass(frozen=True, slots=True)
class TillProduct:
    """One line of a till sale as SumUp reports it."""

    name: str
    quantity: int
    unit_price_cents: int
    """Gross, per piece."""

    def __post_init__(self) -> None:
        if not 1 <= self.quantity <= TILL_QUANTITY_MAX:
            raise InvalidFieldError("quantity", "out_of_range", f"1 to {TILL_QUANTITY_MAX}")
        if self.unit_price_cents < 0:
            raise InvalidFieldError("unit_price_cents", "out_of_range", "not negative")


@dataclass(frozen=True, slots=True)
class TillSale:
    """A successful payment at the till, card or cash, with what was sold."""

    transaction_code: str
    sold_at: datetime
    payment: TillPayment
    total_cents: int
    products: tuple[TillProduct, ...]


def line_state(
    name: str, *, assigned: bool, ignored: bool, quantity: int, booked: int
) -> TillLineState:
    """The state of a line after booking ``booked`` of its ``quantity`` pieces."""
    if is_custom_amount(name):
        return TillLineState.CUSTOM
    if ignored:
        return TillLineState.IGNORED
    if not assigned:
        return TillLineState.UNASSIGNED
    return TillLineState.BOOKED if booked >= quantity else TillLineState.SHORT


@dataclass(slots=True)
class TillItem:
    """A name in the SumUp app and what it sells: a variant, or nothing (``ignored``)."""

    key: str
    name: str
    variant_id: UUID | None
    ignored: bool
    assigned_by: UUID | None
    updated_at: datetime


@dataclass(slots=True)
class TillLine:
    """One line of a till sale as fetched, and how far it was booked."""

    id: UUID
    transaction_code: str
    position: int
    sold_at: datetime
    payment: TillPayment
    name: str
    key: str
    quantity: int
    unit_price_cents: int
    booked: int
    state: TillLineState
    updated_at: datetime

    @property
    def missing(self) -> int:
        """Pieces sold but not yet booked out."""
        return self.quantity - self.booked


@dataclass(slots=True)
class TillState:
    """Where fetching stands: sales from ``since`` on are fetched (with some overlap)."""

    since: datetime
    last_sync_at: datetime | None
    last_error: str
