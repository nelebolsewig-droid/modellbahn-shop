"""Orders in the admin area (``/api/v1/admin/orders``)."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query

from modellbahn.modules.sales.api.deps import (
    OrderManager,
    OrderServiceDep,
    OrderShipper,
    OrderViewer,
)
from modellbahn.modules.sales.api.errors import ORDER_NOT_FOUND, STAFF_ACCESS
from modellbahn.modules.sales.api.schemas import AdminOrderOut, CancelIn, OrderPageOut, ShipIn
from modellbahn.modules.sales.domain.model import OrderStatus
from modellbahn.platform.errors import problems

router = APIRouter(prefix="/admin/orders", tags=["admin-sales"])

_STATE_CONFLICT = {409: ["invalid_order_state"]}


@router.get(
    "",
    operation_id="listOrders",
    summary="Orders, newest first",
    responses=problems(STAFF_ACCESS, unsafe=False),
)
async def list_orders(
    _: OrderViewer,
    service: OrderServiceDep,
    status_filter: Annotated[list[OrderStatus] | None, Query(alias="status")] = None,
    q: Annotated[
        str | None, Query(max_length=200, description="Part of the order number or e-mail.")
    ] = None,
    cursor: Annotated[str | None, Query(max_length=500)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> OrderPageOut:
    page = await service.search(
        statuses=frozenset(status_filter) if status_filter else None,
        text=q,
        cursor=cursor,
        limit=limit,
    )
    return OrderPageOut.from_page(page)


@router.get(
    "/{order_id}",
    operation_id="getOrder",
    summary="An order with lines, address and payments",
    responses=problems({**STAFF_ACCESS, **ORDER_NOT_FOUND}, unsafe=False),
)
async def get_order(order_id: UUID, _: OrderViewer, service: OrderServiceDep) -> AdminOrderOut:
    return AdminOrderOut.from_details(await service.get(order_id))


@router.post(
    "/{order_id}/ship",
    operation_id="shipOrder",
    summary="Ship a paid, completely picked order (the customer gets an e-mail)",
    responses=problems(
        {**STAFF_ACCESS, **ORDER_NOT_FOUND, 409: ["invalid_order_state", "order_not_picked"]}
    ),
)
async def ship_order(
    order_id: UUID, body: ShipIn, _: OrderShipper, service: OrderServiceDep
) -> AdminOrderOut:
    details = await service.ship(
        order_id, carrier=body.carrier, tracking_number=body.tracking_number
    )
    return AdminOrderOut.from_details(details)


@router.post(
    "/{order_id}/cancel",
    operation_id="cancelOrder",
    summary="Cancel an order that has not been shipped; a payment is refunded",
    responses=problems(
        {**STAFF_ACCESS, **ORDER_NOT_FOUND, **_STATE_CONFLICT, 503: ["payment_unavailable"]}
    ),
)
async def cancel_order(
    order_id: UUID, body: CancelIn, _: OrderManager, service: OrderServiceDep
) -> AdminOrderOut:
    return AdminOrderOut.from_details(await service.cancel(order_id, note=body.note))
