"""Outbox event handlers of the inventory module; the worker runs them.

* ``sales.order.paid``: allocate the order (FIFO units, backorders for the rest).
* ``sales.order.cancelled``: give its units back; backorders lapse.
* ``sales.order.shipped``: its picked units leave the workshop.

Delivery is at least once. Allocating does nothing for an order that has its
allocations; releasing and shipping only touch allocations that are still open.
"""

import structlog

from modellbahn.modules.inventory.application.allocation import AllocationService
from modellbahn.modules.inventory.domain.errors import OrderNotAllocatableError
from modellbahn.modules.sales.contracts.events import OrderCancelled, OrderPaid, OrderShipped
from modellbahn.platform.outbox import HandlerRegistry

_logger = structlog.get_logger(__name__)


class InventoryHandlers:
    def __init__(self, *, allocation: AllocationService) -> None:
        self._allocation = allocation

    def register(self, registry: HandlerRegistry) -> None:
        """Subscribe the handlers to their events."""
        registry.register(OrderPaid, self.allocate)
        registry.register(OrderCancelled, self.release)
        registry.register(OrderShipped, self.ship)

    async def allocate(self, event: OrderPaid) -> None:
        try:
            await self._allocation.allocate_order(event.aggregate_id)
        except OrderNotAllocatableError:
            # Cancelled before the worker came to it: nothing to allocate any more.
            _logger.info("inventory.allocate.skipped", order=event.number)

    async def release(self, event: OrderCancelled) -> None:
        await self._allocation.release_order(event.aggregate_id)

    async def ship(self, event: OrderShipped) -> None:
        await self._allocation.ship_order(event.aggregate_id)
