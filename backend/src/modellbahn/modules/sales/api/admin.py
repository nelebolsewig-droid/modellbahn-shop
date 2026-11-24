"""Orders in the admin area (``/api/v1/admin/orders``)."""

from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Response, status
from starlette.concurrency import run_in_threadpool

from modellbahn.modules.sales.api.deps import (
    DeliveryNoteServiceDep,
    InvoiceServiceDep,
    LabelServiceDep,
    OrderManager,
    OrderServiceDep,
    OrderShipper,
    OrderViewer,
    SalesReportServiceDep,
    WithdrawalServiceDep,
    pdf_response,
)
from modellbahn.modules.sales.api.errors import ORDER_NOT_FOUND, STAFF_ACCESS
from modellbahn.modules.sales.api.schemas import (
    AdminOrderOut,
    CancelIn,
    LabelIn,
    OrderPageOut,
    RefundIn,
    RepaymentAccountIn,
    RepaymentListOut,
    RepaymentSummaryOut,
    SalesReportOut,
    ShipIn,
    ShippingLabelOut,
    ShippingSetupOut,
    WithdrawalListOut,
    WithdrawalOut,
    repayment_reference,
)
from modellbahn.modules.sales.domain.errors import OrderNotFoundError
from modellbahn.modules.sales.domain.model import OrderStatus
from modellbahn.platform.bank import BankAccount, girocode_svg
from modellbahn.platform.errors import problems
from modellbahn.platform.pdf_images import pdf_to_pngs

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
        {**STAFF_ACCESS, **ORDER_NOT_FOUND, 409: ["invalid_order_state", "order_pieces_missing"]}
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
    "/{order_id}/making",
    operation_id="startMakingOrder",
    summary="Note that the workshop is making a paid order's pieces (the customer gets an "
    "e-mail, once)",
    responses=problems({**STAFF_ACCESS, **ORDER_NOT_FOUND, **_STATE_CONFLICT}),
)
async def start_making_order(
    order_id: UUID, _: OrderShipper, service: OrderServiceDep
) -> AdminOrderOut:
    return AdminOrderOut.from_details(await service.start_making(order_id))


@router.post(
    "/{order_id}/finishing",
    operation_id="startFinishingOrder",
    summary="Note that a paid order's pieces go into painting and assembly (the customer gets "
    "an e-mail, once)",
    responses=problems({**STAFF_ACCESS, **ORDER_NOT_FOUND, **_STATE_CONFLICT}),
)
async def start_finishing_order(
    order_id: UUID, _: OrderShipper, service: OrderServiceDep
) -> AdminOrderOut:
    return AdminOrderOut.from_details(await service.start_finishing(order_id))


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


@router.put(
    "/{order_id}/repayment",
    operation_id="setRepaymentAccount",
    summary="Where a bank transfer's refund goes back to: holder and IBAN (ADR 0040)",
    description="Typed in from the bank statement, where the customer's transfer came from.",
    responses=problems({**STAFF_ACCESS, **ORDER_NOT_FOUND, **_STATE_CONFLICT}),
)
async def set_repayment_account(
    order_id: UUID, body: RepaymentAccountIn, _: OrderManager, service: OrderServiceDep
) -> AdminOrderOut:
    return AdminOrderOut.from_details(
        await service.set_repayment_account(order_id, holder=body.holder, iban=body.iban)
    )


@router.post(
    "/{order_id}/repayment/done",
    operation_id="markRepaid",
    summary="The refund was transferred back; the account is forgotten (ADR 0040)",
    responses=problems({**STAFF_ACCESS, **ORDER_NOT_FOUND, **_STATE_CONFLICT}),
)
async def mark_repaid(order_id: UUID, _: OrderManager, service: OrderServiceDep) -> AdminOrderOut:
    return AdminOrderOut.from_details(await service.mark_repaid(order_id))


@router.get(
    "/{order_id}/repayment/girocode.svg",
    operation_id="getRepaymentGirocode",
    summary="The GiroCode of an open repayment, for the staff's banking app (ADR 0040)",
    response_class=Response,
    responses={
        200: {"content": {"image/svg+xml": {}}, "description": "The GiroCode."},
        **problems({**STAFF_ACCESS, **ORDER_NOT_FOUND}, unsafe=False),
    },
)
async def get_repayment_girocode(
    order_id: UUID, _: OrderManager, service: OrderServiceDep
) -> Response:
    """Only while a repayment is open and its account is in; otherwise 404."""
    order = (await service.get(order_id)).order
    payment = order.repayment
    if payment is None or payment.repay_holder is None or payment.repay_iban is None:
        raise OrderNotFoundError
    account = BankAccount(holder=payment.repay_holder, iban=payment.repay_iban)
    payload = account.epc_payload(
        amount_cents=payment.repayment_due_cents, reference=repayment_reference(order)
    )
    return Response(
        content=girocode_svg(payload),
        media_type="image/svg+xml",
        headers={"Cache-Control": "no-store"},
    )


repayments_router = APIRouter(prefix="/admin/repayments", tags=["admin-sales"])


@repayments_router.get(
    "",
    operation_id="listRepayments",
    summary="Refunds of bank transfers that still have to be transferred back (ADR 0040)",
    responses=problems(STAFF_ACCESS, unsafe=False, validated=False),
)
async def list_repayments(_: OrderManager, service: OrderServiceDep) -> RepaymentListOut:
    orders = await service.open_repayments()
    return RepaymentListOut(items=[RepaymentSummaryOut.from_order(order) for order in orders])


_LABEL_NOT_FOUND = {404: ["order_not_found", "label_not_found"]}
_INVOICE_NOT_FOUND = {404: ["invoice_not_found"]}


@router.get(
    "/{order_id}/invoices/{invoice_id}/document.pdf",
    operation_id="getInvoiceDocument",
    summary="An invoice or correction of the order as a PDF (ADR 0038)",
    response_class=Response,
    responses={
        200: {"content": {"application/pdf": {}}, "description": "The document."},
        **problems({**STAFF_ACCESS, **_INVOICE_NOT_FOUND}, unsafe=False),
    },
)
async def get_invoice_document(
    order_id: UUID, invoice_id: UUID, _: OrderViewer, invoices: InvoiceServiceDep
) -> Response:
    invoice = await invoices.get(invoice_id, order_id=order_id)
    return pdf_response(invoice.document, invoice.filename)


@router.get(
    "/{order_id}/delivery-note.pdf",
    operation_id="getDeliveryNote",
    summary="The delivery note for the parcel, without prices (ADR 0047)",
    description="Packers too: written anew on every call for a paid or shipped order.",
    response_class=Response,
    responses={
        200: {"content": {"application/pdf": {}}, "description": "The note."},
        **problems({**STAFF_ACCESS, **ORDER_NOT_FOUND, **_STATE_CONFLICT}, unsafe=False),
    },
)
async def get_delivery_note(
    order_id: UUID, _: OrderViewer, notes: DeliveryNoteServiceDep
) -> Response:
    note = await notes.for_order(order_id)
    return pdf_response(note.document, note.filename)


shipping_router = APIRouter(prefix="/admin/shipping", tags=["admin-sales"])


@shipping_router.get(
    "/setup",
    operation_id="getShippingSetup",
    summary="Whether the Stellwerk books shipping labels, and the default weight",
    responses=problems(STAFF_ACCESS, unsafe=False, validated=False),
)
async def shipping_setup(
    _: OrderViewer, labels: LabelServiceDep, invoices: InvoiceServiceDep
) -> ShippingSetupOut:
    return ShippingSetupOut(
        books_labels=labels.books_labels,
        carrier=labels.carrier_name,
        default_weight_g=labels.default_weight_g,
        issues_invoices=invoices.issues_invoices,
    )


@router.post(
    "/{order_id}/shipping-label",
    status_code=status.HTTP_201_CREATED,
    operation_id="bookShippingLabel",
    summary="Book the parcel's label with the carrier (ADR 0023), and ship if asked",
    description="Packers too: whoever packs the parcel prints its label. With `ship` the "
    "order is shipped in the same go (ADR 0028).",
    responses=problems(
        {
            **STAFF_ACCESS,
            **ORDER_NOT_FOUND,
            409: [
                "invalid_order_state",
                "label_exists",
                "carrier_rejected",
                "order_pieces_missing",
            ],
            503: ["carrier_unavailable"],
        }
    ),
)
async def book_shipping_label(
    order_id: UUID, body: LabelIn, _: OrderShipper, labels: LabelServiceDep
) -> ShippingLabelOut:
    label = await labels.book(order_id, weight_g=body.weight_g, ship=body.ship)
    return ShippingLabelOut.from_label(label)


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


@router.get(
    "/{order_id}/shipping-label.png",
    operation_id="getShippingLabelImage",
    summary="The label as a picture at 300 dpi, for label printers whose apps print images",
    response_class=Response,
    responses={
        200: {"content": {"image/png": {}}, "description": "The label."},
        **problems({**STAFF_ACCESS, **_LABEL_NOT_FOUND}, unsafe=False),
    },
)
async def get_shipping_label_image(
    order_id: UUID, _: OrderViewer, labels: LabelServiceDep
) -> Response:
    label = await labels.active(order_id)
    pictures = await run_in_threadpool(pdf_to_pngs, label.document)
    return Response(
        content=pictures[0],
        media_type="image/png",
        headers={
            "Content-Disposition": f'inline; filename="DHL-{label.shipment_number}.png"',
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


# --- Sales report (ADR 0039) ----------------------------------------------------------

report_router = APIRouter(prefix="/admin/sales", tags=["admin-sales"])


@report_router.get(
    "/report",
    operation_id="getSalesReport",
    summary="What was sold between two shop days: paid orders and pieces booked out as sold",
    description="Order lines count on the day they were paid (cancelled orders not); pieces "
    "sold at a fair, on site or privately on the day they were booked out, at the price "
    "entered or else today's shop price (`price_from_shop`). Days in Europe/Berlin, at "
    "most 366.",
    responses=problems(STAFF_ACCESS, unsafe=False),
)
async def get_sales_report(
    _: OrderManager,
    service: SalesReportServiceDep,
    start: Annotated[date, Query(description="First day, inclusive.")],
    end: Annotated[date, Query(description="Last day, inclusive.")],
) -> SalesReportOut:
    return SalesReportOut.from_report(await service.report(start, end))
