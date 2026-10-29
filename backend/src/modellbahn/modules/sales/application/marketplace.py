"""Orders from a marketplace (eBay): sold and paid there, packed and shipped here.

The marketplace module keeps the sale as eBay reported it and announces it; this takes
it over as one of the shop's orders, paid at once, so the inventory allocates it and the
workshop picks it like any other. The buyer hears from eBay, not from the shop: no
e-mails go out for these orders (see the handlers).

A cancellation on eBay follows the same way. eBay refunds the buyer, so the shop only
records it; an order that already left the workshop stays shipped.
"""

import structlog

from modellbahn.modules.marketplace.contracts.events import (
    MarketplaceOrderCancelled,
    MarketplaceOrderReceived,
)
from modellbahn.modules.marketplace.contracts.orders import ReceivedOrder
from modellbahn.modules.sales.application.common import UnitOfWorkFactory
from modellbahn.modules.sales.application.ports import SalesUnitOfWork
from modellbahn.modules.sales.domain.model import (
    CancelReason,
    Order,
    OrderStatus,
    PostalAddress,
    PricedItem,
    SalesChannel,
    order_number,
)
from modellbahn.platform.clock import Clock
from modellbahn.platform.outbox import HandlerRegistry
from modellbahn.platform.security import generate_token
from modellbahn.platform.uow import UniqueViolationError

_logger = structlog.get_logger(__name__)

# Constraints a second order for the same sale runs into (the id and key come from it).
_SAME_SALE = frozenset({"pk_orders", "uq_orders_checkout_key", "orders_external_ref_idx"})


class MarketplaceIntake:
    """Takes marketplace sales over as orders, and follows their cancellation."""

    def __init__(self, *, uow_factory: UnitOfWorkFactory, clock: Clock) -> None:
        self._uow = uow_factory
        self._clock = clock

    def register(self, registry: HandlerRegistry) -> None:
        registry.register(MarketplaceOrderReceived, self.take_over)
        registry.register(MarketplaceOrderCancelled, self.follow_cancellation)

    async def take_over(self, event: MarketplaceOrderReceived) -> None:
        """Create the paid order; delivered twice, the second delivery finds it and stops."""
        try:
            async with self._uow() as uow:
                received = await uow.marketplace.received_order(event.aggregate_id)
                if received is None or received.cancelled:
                    return
                if await uow.orders.get(received.order_id) is not None:
                    return
                order = await self._import(uow, received)
                if order is None:
                    return
                await uow.commit()
        except UniqueViolationError as exc:
            # A parallel delivery of the same event created the order first.
            if exc.constraint not in _SAME_SALE:
                raise
            return
        _logger.info(
            "sales.marketplace_order.imported",
            order=order.number,
            channel=order.channel.value,
            external_ref=order.external_ref,
        )

    async def follow_cancellation(self, event: MarketplaceOrderCancelled) -> None:
        now = self._clock.now()
        async with self._uow() as uow:
            order = await uow.orders.get(event.order_id, for_update=True)
            if order is None or order.status is OrderStatus.CANCELLED:
                return
            if order.status is OrderStatus.SHIPPED:
                # Too late to hold the parcel back: eBay's return process takes over.
                _logger.warning(
                    "sales.marketplace_order.cancelled_after_shipping", order=order.number
                )
                return
            uow.publish(order.cancel(reason=CancelReason.BY_MARKETPLACE, note="", now=now))
            await uow.commit()
        _logger.info("sales.marketplace_order.cancelled", order=order.number)

    async def _import(self, uow: SalesUnitOfWork, received: ReceivedOrder) -> Order | None:
        now = self._clock.now()
        variants = await uow.catalog.sale_variants([line.variant_id for line in received.lines])
        missing = [line.sku for line in received.lines if line.variant_id not in variants]
        if not received.lines or missing:
            # The marketplace matched every line to a variant; one was deleted since.
            _logger.error(
                "sales.marketplace_order.unknown_variant",
                external_ref=received.external_id,
                skus=missing,
            )
            return None
        items = [
            PricedItem(
                variant_id=line.variant_id,
                product_slug=variants[line.variant_id].product_slug,
                sku=variants[line.variant_id].sku,
                title=variants[line.variant_id].title,
                scale_code=variants[line.variant_id].scale_code,
                finish_code=variants[line.variant_id].finish_code,
                # What the buyer paid on eBay, markup included.
                unit_price_cents=line.unit_price_cents,
                quantity=line.quantity,
                image_asset_id=variants[line.variant_id].image_asset_id,
            )
            for line in received.lines
        ]
        order, events = Order.import_paid(
            order_id=received.order_id,
            number=order_number(now.year, await uow.orders.next_serial()),
            public_token=generate_token(),
            channel=SalesChannel(received.channel),
            external_ref=received.external_id,
            items=items,
            email=received.email,
            address=PostalAddress.create(
                recipient=received.recipient,
                street=received.street,
                postal_code=received.postal_code,
                city=received.city,
                country_code=received.country_code,
            ),
            shipping_cents=received.shipping_cents,
            paid_at=received.paid_at,
            now=now,
        )
        uow.orders.add(order)
        uow.publish(*events)
        return order
