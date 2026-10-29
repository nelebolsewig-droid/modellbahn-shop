"""The marketplace's services together, as the API and the worker get them."""

from dataclasses import dataclass

from modellbahn.modules.marketplace.application.access import EbayAccess
from modellbahn.modules.marketplace.application.connection import ConnectionService
from modellbahn.modules.marketplace.application.listings import ListingService
from modellbahn.modules.marketplace.application.orders import MarketplaceOrderService
from modellbahn.modules.marketplace.application.ports import (
    EbayGateway,
    GatewayMode,
    UnitOfWorkFactory,
)


@dataclass(frozen=True, slots=True)
class Marketplace:
    """The marketplace's services, wired to the gateway the settings chose."""

    uow_factory: UnitOfWorkFactory
    gateway: EbayGateway
    access: EbayAccess
    connection: ConnectionService
    listings: ListingService
    orders: MarketplaceOrderService

    @property
    def mode(self) -> GatewayMode:
        return self.gateway.mode

    async def aclose(self) -> None:
        await self.gateway.aclose()
