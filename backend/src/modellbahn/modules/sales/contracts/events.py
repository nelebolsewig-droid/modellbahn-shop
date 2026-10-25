"""Sales events, for other modules to react to (inventory allocates paid orders).

Plain Python like the domain it comes from: importing it keeps a domain layer pure.
"""

from modellbahn.modules.sales.domain.events import (
    OrderCancelled,
    OrderPaid,
    OrderPlaced,
    OrderShipped,
)

__all__ = ["OrderCancelled", "OrderPaid", "OrderPlaced", "OrderShipped"]
