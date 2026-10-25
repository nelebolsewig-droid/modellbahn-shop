"""Whether the shop can deliver a variant, and how soon: the rule shop, cart and checkout share.

* Enough free units on the shelves: *in stock*, ships at once.
* Not enough, but the variant may be backordered: *made to order*, printed for the
  customer, ships later.
* Otherwise *unavailable*: the shop does not sell it right now.
"""

from enum import StrEnum


class Availability(StrEnum):
    IN_STOCK = "in_stock"
    MADE_TO_ORDER = "made_to_order"
    UNAVAILABLE = "unavailable"


def availability(*, free_units: int, wanted: int, allow_backorder: bool) -> Availability:
    """How ``wanted`` pieces of a variant with ``free_units`` on the shelves can be delivered."""
    if wanted <= free_units:
        return Availability.IN_STOCK
    if allow_backorder:
        return Availability.MADE_TO_ORDER
    return Availability.UNAVAILABLE
