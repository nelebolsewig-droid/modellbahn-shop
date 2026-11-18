"""What the store is worth: the finished pieces on the shelves at today's shop price, and
what their material cost to print.

A piece counts while it lies in a place, free or reserved for an order (``ON_SHELF``).
A labelled piece never put away does not lie anywhere yet, and a picked one is sold and
being packed; neither counts. The value is the gross shop price of the piece's variant
as it is now (not the "was" price): what the pieces would bring in the shop today.

The production value (*Herstellwert*, ADR 0035) is the material of each piece: what its
kit takes by the bill of materials, at the price of its materials. Bausatz and
Fertigmodell share one bill of materials, so both cost the same to print; paint and
work are not in it. A piece whose kit lacks an amount or a price counts towards the
pieces without a known cost instead of making the sum look smaller.

Pieces of a variant the catalogue no longer has keep lying but carry no price; they are
counted apart so the sum does not hide them. Printed parts have no price of their own
(they become a model only by assembly), so the store reports their number only.

Pure, so it is tested without a database.
"""

from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID

from modellbahn.modules.catalog.contracts.variants import SaleVariant
from modellbahn.modules.inventory.application.ports import StockCount
from modellbahn.modules.inventory.domain.model import ON_SHELF, UnitStatus


def _cents(amount: Decimal) -> int:
    return int(amount.quantize(Decimal(1), rounding=ROUND_HALF_UP))


@dataclass(frozen=True, slots=True)
class ValueShare:
    """Pieces and their value for one group: an Ausführung, a scale or a model."""

    key: str
    """The finish or scale code, or the product id: stable for sorting and links."""
    name: str
    pieces: int
    value_cents: int
    cost_cents: int = 0
    """Material of the pieces whose cost is known."""
    cost_pieces: int = 0
    """Pieces whose cost is known."""


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
    cost_cents: int = 0
    """Herstellwert: the material of the pieces whose cost is known."""
    cost_pieces: int = 0
    """Pieces whose cost is known; ``pieces - cost_pieces`` lack an amount or a price."""
    cost_value_cents: int = 0
    """Shop value of the pieces whose cost is known: what the cost compares with."""


class _Tally:
    __slots__ = ("cost", "cost_pieces", "names", "pieces", "value")

    def __init__(self) -> None:
        self.names: dict[str, str] = {}
        self.pieces: dict[str, int] = defaultdict(int)
        self.value: dict[str, int] = defaultdict(int)
        self.cost: dict[str, Decimal] = defaultdict(Decimal)
        self.cost_pieces: dict[str, int] = defaultdict(int)

    def add(self, key: str, name: str, pieces: int, value: int, cost: Decimal | None) -> None:
        self.names.setdefault(key, name)
        self.pieces[key] += pieces
        self.value[key] += value
        if cost is not None:
            self.cost[key] += cost
            self.cost_pieces[key] += pieces

    def shares(self) -> list[ValueShare]:
        rows = [
            ValueShare(
                key=key,
                name=name,
                pieces=self.pieces[key],
                value_cents=self.value[key],
                cost_cents=_cents(self.cost[key]),
                cost_pieces=self.cost_pieces[key],
            )
            for key, name in self.names.items()
        ]
        rows.sort(key=lambda row: (-row.value_cents, -row.pieces, row.name, row.key))
        return rows


def stock_value(
    counts: Iterable[StockCount],
    variants: Mapping[UUID, SaleVariant],
    part_totals: Mapping[UUID, int],
    kit_costs: Mapping[UUID, Decimal | None] | None = None,
) -> StockValue:
    """The store's value from unit counts per variant and state, the parts' totals and
    the material cost of one kit per product scale (missing or ``None``: unknown)."""
    costs = kit_costs or {}
    free_pieces = free_cents = reserved_pieces = reserved_cents = unpriced = 0
    cost_total = Decimal(0)
    cost_pieces = cost_value = 0
    finishes, scales, models = _Tally(), _Tally(), _Tally()
    for count in counts:
        if count.status not in ON_SHELF or count.count <= 0:
            continue
        variant = variants.get(count.variant_id)
        if variant is None:
            unpriced += count.count
            continue
        value = variant.price_cents * count.count
        kit_cost = costs.get(variant.product_scale_id)
        cost = kit_cost * count.count if kit_cost is not None else None
        if count.status is UnitStatus.IN_STOCK:
            free_pieces += count.count
            free_cents += value
        else:
            reserved_pieces += count.count
            reserved_cents += value
        if cost is not None:
            cost_total += cost
            cost_pieces += count.count
            cost_value += value
        finishes.add(variant.finish_code, variant.finish_name, count.count, value, cost)
        scales.add(variant.scale_code, variant.scale_name, count.count, value, cost)
        models.add(str(variant.product_id), variant.product_name, count.count, value, cost)
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
        cost_cents=_cents(cost_total),
        cost_pieces=cost_pieces,
        cost_value_cents=cost_value,
    )
