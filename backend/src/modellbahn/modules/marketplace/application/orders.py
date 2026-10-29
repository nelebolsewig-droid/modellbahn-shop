"""Use cases of the orders from eBay: fetching them, and telling eBay what was shipped.

The worker asks eBay every two minutes for orders changed since the last time (with an
overlap, as eBay's change dates may lag). A new paid order is kept and handed to the
sales module, which makes it one of the shop's orders; a cancelled one is followed.
Shipping that order reports carrier and tracking number back to eBay.
"""

from dataclasses import dataclass
from datetime import timedelta
from typing import Final
from uuid import UUID

import structlog

from modellbahn.modules.marketplace.application.access import EbayAccess
from modellbahn.modules.marketplace.application.ports import (
    AccessTokenRejectedError,
    EbayGateway,
    ExternalOrder,
    GatewayMode,
    MarketplaceRejectedError,
    ShipmentReport,
    UnitOfWorkFactory,
)
from modellbahn.modules.marketplace.domain.errors import (
    ListingNotFoundError,
    MarketplaceOrderNotFoundError,
    NotConnectedError,
    TestModeOnlyError,
)
from modellbahn.modules.marketplace.domain.model import (
    EBAY,
    MarketplaceOrder,
    MarketplaceOrderStatus,
    ReceivedLine,
)
from modellbahn.platform.clock import Clock
from modellbahn.platform.uow import UniqueViolationError

_logger = structlog.get_logger(__name__)

# eBay's change dates may show up a little late; the next fetch looks back this far.
FETCH_OVERLAP: Final = timedelta(minutes=10)
# The first fetch after connecting looks back this far.
FIRST_FETCH: Final = timedelta(days=2)
RECENT_LIMIT: Final = 50


@dataclass(frozen=True, slots=True)
class OrderView:
    order: MarketplaceOrder
    order_number: str | None
    """The shop's number, once the sales module made the order."""


class MarketplaceOrderService:
    def __init__(
        self,
        *,
        uow_factory: UnitOfWorkFactory,
        gateway: EbayGateway,
        access: EbayAccess,
        clock: Clock,
        test_shipping_cents: int,
    ) -> None:
        self._uow = uow_factory
        self._gateway = gateway
        self._access = access
        self._clock = clock
        self._test_shipping_cents = test_shipping_cents

    async def recent(self) -> list[OrderView]:
        async with self._uow() as uow:
            orders = await uow.orders.recent(RECENT_LIMIT)
            numbers = await uow.sales.order_numbers([order.order_id for order in orders])
        return [
            OrderView(order=order, order_number=numbers.get(order.order_id)) for order in orders
        ]

    async def fetch(self) -> int:
        """Take over the orders eBay changed since the last fetch; how many were new."""
        async with self._uow() as uow:
            account = await uow.account.get()
            if account is None or not account.is_connected:
                return 0
            checked_until = account.orders_checked_until
        try:
            token = await self._access.token()
        except NotConnectedError:
            return 0
        until = self._clock.now()
        since = checked_until - FETCH_OVERLAP if checked_until is not None else until - FIRST_FETCH
        try:
            orders = await self._gateway.orders(token, modified_since=since, until=until)
        except AccessTokenRejectedError:
            await self._access.rejected()
            raise
        received = 0
        for order in orders:
            if await self._take(order):
                received += 1
        async with self._uow() as uow:
            account = await uow.account.get(for_update=True)
            if account is not None:
                account.orders_checked(until, self._clock.now())
                await uow.commit()
        if received:
            _logger.info("marketplace.orders.received", count=received)
        return received

    async def report_shipment(self, order_id: UUID) -> MarketplaceOrder | None:
        """Tell eBay how the shop's order went out (None if it is not from eBay)."""
        try:
            token = await self._access.token()
        except NotConnectedError:
            token = ""
        async with self._uow() as uow:
            order = await uow.orders.by_order_id(order_id, for_update=True)
            if order is None or order.status is not MarketplaceOrderStatus.RECEIVED:
                return order
            shipment = await uow.sales.shipment(order.order_id)
            if shipment is None:
                return order
            now = self._clock.now()
            if not token:
                order.shipment_failed("Keine Verbindung zu eBay.", now)
            else:
                try:
                    await self._gateway.report_shipment(
                        token,
                        ShipmentReport(
                            external_id=order.external_id,
                            lines=[(line.line_ref, line.quantity) for line in order.lines],
                            carrier=shipment.carrier,
                            tracking_number=shipment.tracking_number,
                            shipped_at=shipment.shipped_at,
                        ),
                    )
                    order.shipment_reported(now)
                except AccessTokenRejectedError:
                    await self._access.rejected()
                    raise
                except MarketplaceRejectedError as exc:
                    order.shipment_failed(exc.message or exc.code, now)
            await uow.commit()
        _logger.info(
            "marketplace.shipment.reported",
            external_id=order.external_id,
            status=order.status.value,
            problem=bool(order.problem),
        )
        return order

    async def report_again(self, marketplace_order_id: UUID) -> MarketplaceOrder:
        async with self._uow() as uow:
            order = await uow.orders.get(marketplace_order_id)
        if order is None:
            raise MarketplaceOrderNotFoundError
        return await self.report_shipment(order.order_id) or order

    # --- The built-in test marketplace ------------------------------------------------

    async def sell_test(self, *, sku: str, quantity: int) -> str:
        """Buy on the test marketplace as an eBay buyer would; the order arrives at once."""
        if self._gateway.mode is not GatewayMode.TEST:
            raise TestModeOnlyError
        now = self._clock.now()
        async with self._uow() as uow:
            offered = await uow.listings.item_for_sku(sku)
            if offered is None:
                raise ListingNotFoundError
            _, price_cents = offered
            external_id = await uow.test_marketplace.sell(
                sku=sku,
                quantity=quantity,
                unit_price_cents=price_cents,
                shipping_cents=self._test_shipping_cents,
                now=now,
            )
            await uow.commit()
        await self.fetch()
        return external_id

    async def cancel_test(self, external_id: str) -> None:
        if self._gateway.mode is not GatewayMode.TEST:
            raise TestModeOnlyError
        async with self._uow() as uow:
            if not await uow.test_marketplace.cancel(external_id, self._clock.now()):
                raise MarketplaceOrderNotFoundError
            await uow.commit()
        await self.fetch()

    # --- Taking orders over -----------------------------------------------------------

    async def _take(self, external: ExternalOrder) -> bool:
        """Keep a new paid order, or follow a change of a known one; True if it was new."""
        now = self._clock.now()
        try:
            async with self._uow() as uow:
                known = await uow.orders.by_external(EBAY, external.external_id, for_update=True)
                if known is not None:
                    if external.cancelled:
                        uow.publish(*known.cancel(now))
                        await uow.commit()
                    return False
                if external.cancelled or not external.paid:
                    # Unpaid orders come again once paid (that changes them).
                    return False
                variants = await uow.catalog.variants_by_sku([line.sku for line in external.lines])
                problem = uow.sales.address_problem(
                    recipient=external.recipient,
                    street=external.street,
                    postal_code=external.postal_code,
                    city=external.city,
                    country_code=external.country_code,
                ) or ("" if external.lines else "no lines")
                order, events = MarketplaceOrder.receive(
                    channel=EBAY,
                    external_id=external.external_id,
                    buyer_name=external.buyer_name,
                    # eBay may withhold the address; the shop writes to its buyers via eBay
                    # anyway, so a reserved domain stands in where it is missing.
                    email=external.email or f"ebay-{external.external_id}@marketplace.invalid",
                    recipient=external.recipient,
                    street=external.street,
                    postal_code=external.postal_code,
                    city=external.city,
                    country_code=external.country_code,
                    shipping_cents=external.shipping_cents,
                    paid_at=external.paid_at or now,
                    lines=[
                        ReceivedLine(
                            line_ref=line.line_ref,
                            sku=line.sku,
                            variant_id=(
                                variants[line.sku].variant_id if line.sku in variants else None
                            ),
                            title=line.title,
                            quantity=line.quantity,
                            unit_price_cents=line.unit_price_cents,
                        )
                        for line in external.lines
                    ],
                    problem=problem,
                    now=now,
                )
                uow.orders.add(order)
                uow.publish(*events)
                await uow.commit()
        except UniqueViolationError as exc:
            # Two fetches at once: the other one kept it.
            if exc.constraint != "uq_marketplace_orders_channel_external_id":
                raise
            return False
        if order.status is MarketplaceOrderStatus.REJECTED:
            _logger.warning(
                "marketplace.order.rejected", external_id=order.external_id, problem=order.problem
            )
        return True
