"""Orders in the admin area (``/api/v1/admin/orders``)."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Response, status

from modellbahn.modules.sales.api.deps import (
    LabelServiceDep,
    OrderManager,
    OrderServiceDep,
    OrderShipper,
    OrderViewer,
    WithdrawalServiceDep,
)
from modellbahn.modules.sales.api.errors import ORDER_NOT_FOUND, STAFF_ACCESS
from modellbahn.modules.sales.api.schemas import (
    AdminOrderOut,
    CancelIn,
    LabelIn,
    OrderPageOut,
    RefundIn,
    ShipIn,
    ShippingLabelOut,
    ShippingSetupOut,
    WithdrawalListOut,
    WithdrawalOut,
)
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
        str | None,
        Query(
            max_length=200,
            description="Part of the order number, the e-mail or eBay's order number.",
        ),
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
    description="An order from eBay is cancelled on eBay; the shop follows by itself.",
    responses=problems(
        {
            **STAFF_ACCESS,
            **ORDER_NOT_FOUND,
            409: ["invalid_order_state", "marketplace_order", "refund_rejected"],
            503: ["payment_unavailable"],
        }
    ),
)
async def cancel_order(
    order_id: UUID, body: CancelIn, _: OrderManager, service: OrderServiceDep
) -> AdminOrderOut:
    return AdminOrderOut.from_details(
        await service.cancel(order_id, note=body.note, refunded_by_hand=body.refunded_by_hand)
    )


@router.post(
    "/{order_id}/bank-transfer",
    operation_id="confirmBankTransfer",
    summary="The customer's bank transfer is in the account: the order is paid",
    description="Payment in advance (ADR 0022). The customer gets the usual confirmation.",
    responses=problems({**STAFF_ACCESS, **ORDER_NOT_FOUND, 409: ["invalid_order_state"]}),
)
async def confirm_bank_transfer(
    order_id: UUID, _: OrderManager, service: OrderServiceDep
) -> AdminOrderOut:
    return AdminOrderOut.from_details(await service.confirm_bank_transfer(order_id))


@router.post(
    "/{order_id}/refunds",
    operation_id="refundOrder",
    summary="Give money back after a return (the customer gets an e-mail)",
    responses=problems(
        {
            **STAFF_ACCESS,
            **ORDER_NOT_FOUND,
            409: ["refund_not_possible", "marketplace_order", "refund_rejected"],
            503: ["payment_unavailable"],
        }
    ),
)
async def refund_order(
    order_id: UUID, body: RefundIn, _: OrderManager, service: OrderServiceDep
) -> AdminOrderOut:
    """The payment provider refunds at once; at most what is left of the payment. A whole
    order that has not been shipped is cancelled instead (``cancelOrder``)."""
    return AdminOrderOut.from_details(
        await service.refund(
            order_id, amount_cents=body.amount_cents, refunded_by_hand=body.refunded_by_hand
        )
    )


_LABEL_NOT_FOUND = {404: ["order_not_found", "label_not_found"]}


shipping_router = APIRouter(prefix="/admin/shipping", tags=["admin-sales"])


@shipping_router.get(
    "/setup",
    operation_id="getShippingSetup",
    summary="Whether the Stellwerk books shipping labels, and the default weight",
    responses=problems(STAFF_ACCESS, unsafe=False, validated=False),
)
async def shipping_setup(_: OrderViewer, labels: LabelServiceDep) -> ShippingSetupOut:
    return ShippingSetupOut(
        books_labels=labels.books_labels,
        carrier=labels.carrier_name,
        default_weight_g=labels.default_weight_g,
    )


@router.post(
    "/{order_id}/shipping-label",
    status_code=status.HTTP_201_CREATED,
    operation_id="bookShippingLabel",
    summary="Book the parcel's label with the carrier (ADR 0023)",
    description="Packers too: whoever packs the parcel prints its label.",
    responses=problems(
        {
            **STAFF_ACCESS,
            **ORDER_NOT_FOUND,
            409: ["invalid_order_state", "label_exists", "carrier_rejected"],
            503: ["carrier_unavailable"],
        }
    ),
)
async def book_shipping_label(
    order_id: UUID, body: LabelIn, _: OrderShipper, labels: LabelServiceDep
) -> ShippingLabelOut:
    return ShippingLabelOut.from_label(await labels.book(order_id, weight_g=body.weight_g))


@router.get(
    "/{order_id}/shipping-label",
    operation_id="getShippingLabel",
    summary="The order's shipping label in force",
    responses=problems({**STAFF_ACCESS, **_LABEL_NOT_FOUND}, unsafe=False),
)
async def get_shipping_label(
    order_id: UUID, _: OrderViewer, labels: LabelServiceDep
) -> ShippingLabelOut:
    return ShippingLabelOut.from_label(await labels.active(order_id))


@router.get(
    "/{order_id}/shipping-label.pdf",
    operation_id="getShippingLabelDocument",
    summary="The label as a PDF, to print on the label printer",
    response_class=Response,
    responses={
        200: {"content": {"application/pdf": {}}, "description": "The label."},
        **problems({**STAFF_ACCESS, **_LABEL_NOT_FOUND}, unsafe=False),
    },
)
async def get_shipping_label_document(
    order_id: UUID, _: OrderViewer, labels: LabelServiceDep
) -> Response:
    label = await labels.active(order_id)
    return Response(
        content=label.document,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="DHL-{label.shipment_number}.pdf"',
            "Cache-Control": "no-store",
        },
    )


@router.delete(
    "/{order_id}/shipping-label",
    status_code=status.HTTP_204_NO_CONTENT,
    operation_id="cancelShippingLabel",
    summary="Cancel the label at the carrier, e.g. after a wrong weight",
    responses=problems(
        {
            **STAFF_ACCESS,
            **_LABEL_NOT_FOUND,
            409: ["invalid_order_state", "carrier_rejected"],
            503: ["carrier_unavailable"],
        }
    ),
)
async def cancel_shipping_label(
    order_id: UUID, _: OrderShipper, labels: LabelServiceDep
) -> Response:
    await labels.cancel(order_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


withdrawals_router = APIRouter(prefix="/admin/withdrawals", tags=["admin-sales"])


@withdrawals_router.get(
    "",
    operation_id="listWithdrawals",
    summary="Declarations of withdrawal, newest first (§ 356a BGB)",
    responses=problems(STAFF_ACCESS, unsafe=False),
)
async def list_withdrawals(
    _: OrderViewer,
    service: WithdrawalServiceDep,
    order_id: Annotated[
        UUID | None, Query(description="Only the declarations that name this order.")
    ] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> WithdrawalListOut:
    views = await service.recent(limit=limit, order_id=order_id)
    return WithdrawalListOut(items=[WithdrawalOut.from_view(view) for view in views])
