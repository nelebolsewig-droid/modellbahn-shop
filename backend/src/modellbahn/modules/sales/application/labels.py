"""Shipping labels from the Stellwerk (ADR 0023): book, print, cancel.

The staff book the label once the parcel is packed; the carrier answers with its shipment
number and the PDF. Dispatching the order then takes that number by itself, so it reaches
the customer's e-mail. A label booked by mistake is cancelled at the carrier; cancelling
the order cancels its label too (from the worker, so that a carrier hiccup is retried).
"""

from uuid import UUID

import structlog

from modellbahn.modules.sales.application.common import UnitOfWorkFactory
from modellbahn.modules.sales.application.ports import Carrier, LabelRequest, SalesUnitOfWork
from modellbahn.modules.sales.domain.errors import (
    CarrierRejectedError,
    CarrierUnavailableError,
    InvalidOrderStateError,
    LabelExistsError,
    LabelNotFoundError,
    OrderNotFoundError,
)
from modellbahn.modules.sales.domain.events import OrderCancelled
from modellbahn.modules.sales.domain.labels import (
    LabelAddress,
    ShippingLabel,
    check_labelable,
    check_weight,
    product_for,
)
from modellbahn.modules.sales.domain.model import Order, OrderStatus
from modellbahn.platform.clock import Clock
from modellbahn.platform.outbox import HandlerRegistry

_logger = structlog.get_logger(__name__)


class ShippingLabelService:
    def __init__(
        self,
        *,
        uow_factory: UnitOfWorkFactory,
        clock: Clock,
        carrier: Carrier,
        shipper: LabelAddress | None,
        default_weight_g: int,
    ) -> None:
        self._uow = uow_factory
        self._clock = clock
        self._carrier = carrier
        self._shipper = shipper
        self._default_weight_g = default_weight_g

    @property
    def carrier_name(self) -> str:
        return self._carrier.name

    @property
    def books_labels(self) -> bool:
        """A carrier is connected and the shop knows its own address (the imprint)."""
        return self._carrier.books_labels and self._shipper is not None

    @property
    def default_weight_g(self) -> int:
        return self._default_weight_g

    async def book(self, order_id: UUID, *, weight_g: int | None = None) -> ShippingLabel:
        """Book the label of a paid order; one in force per order."""
        if self._shipper is None or not self._carrier.books_labels:
            raise CarrierUnavailableError
        async with self._uow() as uow:
            order = await _locked(uow, order_id)
            check_labelable(order)
            if await uow.labels.active_for(order.id) is not None:
                raise LabelExistsError
            weight = check_weight(weight_g if weight_g is not None else self._default_weight_g)
            product = product_for(order.shipping_address.country_code)
            booked = await self._carrier.book(
                LabelRequest(
                    reference=order.number,
                    product=product,
                    shipper=self._shipper,
                    consignee=LabelAddress.of(order.shipping_address),
                    weight_g=weight,
                )
            )
            label = ShippingLabel.book(
                order=order,
                carrier=self._carrier.name,
                product=product,
                shipment_number=booked.shipment_number,
                weight_g=weight,
                print_format=booked.print_format,
                document=booked.document,
                now=self._clock.now(),
            )
            uow.labels.add(label)
            await uow.commit()
        _logger.info(
            "sales.label.booked",
            order=order.number,
            shipment=label.shipment_number,
            product=product.value,
        )
        return label

    async def active(self, order_id: UUID) -> ShippingLabel:
        async with self._uow() as uow:
            label = await uow.labels.active_for(order_id)
            if label is None:
                raise LabelNotFoundError
            return label

    async def cancel(self, order_id: UUID) -> None:
        """Drop the order's label at the carrier, e.g. after a wrong weight or address.

        Not once the order is shipped: the parcel is on its way with this label.
        """
        async with self._uow() as uow:
            order = await _locked(uow, order_id)
            if order.status is OrderStatus.SHIPPED:
                msg = "a shipped order keeps its label"
                raise InvalidOrderStateError(msg)
            label = await uow.labels.active_for(order_id, for_update=True)
            if label is None:
                raise LabelNotFoundError
            await self._carrier.cancel(label.shipment_number)
            label.cancel(self._clock.now())
            await uow.commit()
        _logger.info("sales.label.cancelled", shipment=label.shipment_number)

    async def cancel_with_order(self, event: OrderCancelled) -> None:
        """A cancelled order's label goes too; the outbox tries again if the carrier is down."""
        async with self._uow() as uow:
            label = await uow.labels.active_for(event.aggregate_id, for_update=True)
            if label is None:
                return
            try:
                if not self._carrier.books_labels:
                    # DHL was switched off since: the label is dropped here, never used.
                    _logger.warning("sales.label.cancel_skipped", shipment=label.shipment_number)
                else:
                    await self._carrier.cancel(label.shipment_number)
            except CarrierRejectedError as error:
                # The carrier no longer knows it (cancelled there, or never used): it is gone.
                _logger.warning(
                    "sales.label.cancel_refused",
                    shipment=label.shipment_number,
                    reason=error.reason,
                )
            label.cancel(self._clock.now())
            await uow.commit()
        _logger.info("sales.label.cancelled_with_order", order=event.number)

    def register(self, registry: HandlerRegistry) -> None:
        registry.register(OrderCancelled, self.cancel_with_order)


async def _locked(uow: SalesUnitOfWork, order_id: UUID) -> Order:
    order = await uow.orders.get(order_id, for_update=True)
    if order is None:
        raise OrderNotFoundError
    return order
