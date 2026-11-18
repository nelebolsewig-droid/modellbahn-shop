"""What the store is worth: the finished pieces on the shelves at today's shop price.

A piece counts while it lies in a place, free or reserved for an order (``ON_SHELF``).
A labelled piece never put away does not lie anywhere yet, and a picked one is sold and
being packed; neither counts. The value is the gross shop price of the piece's variant
as it is now (not the "was" price): what the pieces would bring in the shop today.

Pieces of a variant the catalogue no longer has keep lying but carry no price; they are
counted apart so the sum does not hide them. Printed parts have no price of their own
(they become a model only by assembly), so the store reports their number only.

Pure, so it is tested without a database.
"""

from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from uuid import UUID

from modellbahn.modules.catalog.contracts.variants import SaleVariant
from modellbahn.modules.inventory.application.ports import StockCount
from modellbahn.modules.inventory.domain.model import ON_SHELF, UnitStatus


@dataclass(frozen=True, slots=True)
class ValueShare:
    """Pieces and their value for one group: an Ausführung, a scale or a model."""

    key: str
    """The finish or scale code, or the product id: stable for sorting and links."""
    name: str
    pieces: int
    value_cents: int


@dataclass(frozen=True, slots=True)
class StockValue:
    pieces: int
    """Finished pieces lying in the store, free and reserved."""
    value_cents: int
    free_pieces: int
    free_cents: int
    """The part the shop can still sell; the rest is promised to orders."""
    reserved_pieces: int
    reserved_cents: int
    unpriced_pieces: int
    """Pieces of variants the catalogue no longer has: not in the value."""
    by_finish: list[ValueShare]
    by_scale: list[ValueShare]
    by_model: list[ValueShare]
    """Every model with pieces, the most valuable first."""
    part_pieces: int
    """Printed parts in the boxes, all parts together."""
    part_kinds: int
    """Different parts among them."""


class _Tally:
    __slots__ = ("names", "pieces", "value")

    def __init__(self) -> None:
        self.names: dict[str, str] = {}
        self.pieces: dict[str, int] = defaultdict(int)
        self.value: dict[str, int] = defaultdict(int)

    def add(self, key: str, name: str, pieces: int, value: int) -> None:
        self.names.setdefault(key, name)
        self.pieces[key] += pieces
        self.value[key] += value

    def shares(self) -> list[ValueShare]:
        rows = [
            ValueShare(key=key, name=name, pieces=self.pieces[key], value_cents=self.value[key])
            for key, name in self.names.items()
        ]
        rows.sort(key=lambda row: (-row.value_cents, -row.pieces, row.name, row.key))
        return rows


def stock_value(
    counts: Iterable[StockCount],
    variants: Mapping[UUID, SaleVariant],
    part_totals: Mapping[UUID, int],
) -> StockValue:
    """The store's value from unit counts per variant and state, and the parts' totals."""
    free_pieces = free_cents = reserved_pieces = reserved_cents = unpriced = 0
    finishes, scales, models = _Tally(), _Tally(), _Tally()
    for count in counts:
        if count.status not in ON_SHELF or count.count <= 0:
            continue
        variant = variants.get(count.variant_id)
        if variant is None:
            unpriced += count.count
            continue
        value = variant.price_cents * count.count
        if count.status is UnitStatus.IN_STOCK:
            free_pieces += count.count
            free_cents += value
        else:
            reserved_pieces += count.count
            reserved_cents += value
        finishes.add(variant.finish_code, variant.finish_name, count.count, value)
        scales.add(variant.scale_code, variant.scale_name, count.count, value)
        models.add(str(variant.product_id), variant.product_name, count.count, value)
    parts = [quantity for quantity in part_totals.values() if quantity > 0]
    return StockValue(
        pieces=free_pieces + reserved_pieces,
        value_cents=free_cents + reserved_cents,
        free_pieces=free_pieces,
        free_cents=free_cents,
        reserved_pieces=reserved_pieces,
        reserved_cents=reserved_cents,
        unpriced_pieces=unpriced,
        by_finish=finishes.shares(),
        by_scale=scales.shares(),
        by_model=models.shares(),
        part_pieces=sum(parts),
        part_kinds=len(parts),
    )
