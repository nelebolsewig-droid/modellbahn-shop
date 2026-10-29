"""Outbox event handlers of the marketplace module; the worker runs them.

* Catalogue and stock events: the listings of the product or variant are due for a sync
  (the periodic job does it, so a burst of changes costs one sync).
* A shipped order from eBay: carrier and tracking number go back to eBay. If eBay
  cannot be reached, the handler fails and the outbox tries again later.
"""

from modellbahn.modules.catalog.contracts.events import (
    ProductArchived,
    ProductPublished,
    ProductUpdated,
)
from modellbahn.modules.inventory.contracts.events import StockChanged
from modellbahn.modules.marketplace.application.orders import MarketplaceOrderService
from modellbahn.modules.marketplace.application.ports import UnitOfWorkFactory
from modellbahn.modules.sales.contracts.events import OrderShipped
from modellbahn.platform.clock import Clock
from modellbahn.platform.outbox import HandlerRegistry


class MarketplaceHandlers:
    def __init__(
        self, *, uow_factory: UnitOfWorkFactory, orders: MarketplaceOrderService, clock: Clock
    ) -> None:
        self._uow = uow_factory
        self._orders = orders
        self._clock = clock

    def register(self, registry: HandlerRegistry) -> None:
        registry.register(ProductUpdated, self.product_changed)
        registry.register(ProductPublished, self.product_changed)
        registry.register(ProductArchived, self.product_changed)
        registry.register(StockChanged, self.stock_changed)
        registry.register(OrderShipped, self.order_shipped)

    async def product_changed(
        self, event: ProductUpdated | ProductPublished | ProductArchived
    ) -> None:
        async with self._uow() as uow:
            await uow.listings.mark_due_for_product(event.aggregate_id, self._clock.now())
            await uow.commit()

    async def stock_changed(self, event: StockChanged) -> None:
        async with self._uow() as uow:
            await uow.listings.mark_due_for_variants([event.variant_id], self._clock.now())
            await uow.commit()

    async def order_shipped(self, event: OrderShipped) -> None:
        await self._orders.report_shipment(event.aggregate_id)
