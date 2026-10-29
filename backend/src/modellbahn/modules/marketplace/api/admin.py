"""Stellwerk routes of the marketplace: the eBay connection, offers, orders, test sales."""

from html import escape
from typing import Annotated, Final
from uuid import UUID

import structlog
from fastapi import APIRouter, Path, Query, status
from fastapi.responses import HTMLResponse

from modellbahn.modules.marketplace.api.deps import (
    AccountDeletionsDep,
    EbayOwner,
    ListingEditor,
    MarketplaceDep,
    OptionalMarketplaceDep,
)
from modellbahn.modules.marketplace.api.errors import EBAY_OFF, EBAY_UNAVAILABLE, STAFF_ACCESS
from modellbahn.modules.marketplace.api.schemas import (
    AccountDeletionSetupOut,
    CategoryMappingListIn,
    CategoryMappingListOut,
    CategoryMappingOut,
    ConnectOut,
    EbayStatusOut,
    FetchOut,
    ListingListOut,
    ListingOut,
    ListingPageOut,
    MarketplaceOrderListOut,
    MarketplaceOrderOut,
    PoliciesOut,
    SettingsIn,
    TestAccountClosedOut,
    TestSaleIn,
    TestSaleOut,
    WantIn,
)
from modellbahn.modules.marketplace.application.connection import SettingsChange
from modellbahn.modules.marketplace.application.orders import OrderView
from modellbahn.modules.marketplace.application.ports import (
    MarketplaceRejectedError,
    MarketplaceUnavailableError,
)
from modellbahn.modules.marketplace.domain.errors import ConnectionStateInvalidError
from modellbahn.platform.errors import problems

_logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/admin/marketplace/ebay", tags=["admin-marketplace"])

_OFF: Final = {409: [EBAY_OFF]}
_NOT_CONNECTED: Final = {409: [EBAY_OFF, "ebay_not_connected"]}
# Where the callback sends the owner back to (the Stellwerk's eBay page).
_STELLWERK_PAGE: Final = "/admin/ebay"


@router.get(
    "",
    operation_id="getEbayStatus",
    summary="The eBay connection and its settings",
    responses=problems(STAFF_ACCESS, unsafe=False, validated=False),
)
async def get_status(_: ListingEditor, marketplace: OptionalMarketplaceDep) -> EbayStatusOut:
    if marketplace is None:
        return EbayStatusOut.off()
    return EbayStatusOut.from_account(await marketplace.connection.status(), marketplace.mode)


@router.post(
    "/connect",
    operation_id="connectEbay",
    summary="Start connecting: the address of eBay's consent page",
    responses=problems({**STAFF_ACCESS, **_OFF}, validated=False),
)
async def connect(_: EbayOwner, marketplace: MarketplaceDep) -> ConnectOut:
    return ConnectOut(authorize_url=await marketplace.connection.begin_connect())


@router.get("/callback", include_in_schema=False, response_class=HTMLResponse)
async def callback(
    marketplace: MarketplaceDep,
    code: Annotated[str, Query(max_length=2048)] = "",
    state: Annotated[str, Query(max_length=256)] = "",
    error: Annotated[str, Query(max_length=128)] = "",
) -> HTMLResponse:
    """eBay sends the owner back here; no staff cookie arrives (it is SameSite=Strict).

    The state proves the answer belongs to a connection the owner started in the
    Stellwerk. A small page then leads on to the Stellwerk: a navigation that starts on
    this site carries the cookie again.
    """
    if error or not code:
        return _handoff("abgebrochen", "Die Verbindung mit eBay wurde nicht erteilt.")
    try:
        await marketplace.connection.complete_connect(code=code, state=state)
    except ConnectionStateInvalidError:
        return _handoff("ungueltig", "Dieser Rücksprung von eBay ist abgelaufen oder unbekannt.")
    except (MarketplaceRejectedError, MarketplaceUnavailableError) as exc:
        _logger.warning("marketplace.ebay.connect_failed", error=type(exc).__name__)
        return _handoff("fehler", "eBay hat die Verbindung nicht bestätigt.")
    return _handoff("verbunden", "eBay ist verbunden.")


@router.post(
    "/disconnect",
    operation_id="disconnectEbay",
    summary="Take every offer off eBay and forget the connection",
    responses=problems({**STAFF_ACCESS, **_NOT_CONNECTED, **EBAY_UNAVAILABLE}, validated=False),
)
async def disconnect(_: EbayOwner, marketplace: MarketplaceDep) -> EbayStatusOut:
    account = await marketplace.connection.disconnect()
    return EbayStatusOut.from_account(account, marketplace.mode)


@router.put(
    "/settings",
    operation_id="changeEbaySettings",
    summary="Change policies, markup and the made-to-order quantity",
    responses=problems({**STAFF_ACCESS, **_OFF}),
)
async def change_settings(
    body: SettingsIn, _: EbayOwner, marketplace: MarketplaceDep
) -> EbayStatusOut:
    account = await marketplace.connection.change_settings(
        SettingsChange(
            fulfillment_policy_id=body.fulfillment_policy_id,
            payment_policy_id=body.payment_policy_id,
            return_policy_id=body.return_policy_id,
            price_markup_percent=body.price_markup_percent,
            made_to_order_quantity=body.made_to_order_quantity,
        )
    )
    return EbayStatusOut.from_account(account, marketplace.mode)


@router.get(
    "/policies",
    operation_id="listEbayPolicies",
    summary="The business policies of the eBay account",
    responses=problems(
        {**STAFF_ACCESS, **_NOT_CONNECTED, **EBAY_UNAVAILABLE}, unsafe=False, validated=False
    ),
)
async def list_policies(_: EbayOwner, marketplace: MarketplaceDep) -> PoliciesOut:
    return PoliciesOut.from_policies(await marketplace.connection.policies())


@router.post(
    "/location",
    operation_id="createEbayLocation",
    summary="Create the shop's location on eBay again (from the imprint's address)",
    responses=problems({**STAFF_ACCESS, **_NOT_CONNECTED, **EBAY_UNAVAILABLE}, validated=False),
)
async def create_location(_: EbayOwner, marketplace: MarketplaceDep) -> EbayStatusOut:
    account = await marketplace.connection.create_location()
    return EbayStatusOut.from_account(account, marketplace.mode)


@router.get(
    "/categories",
    operation_id="listEbayCategories",
    summary="The shop's categories with their eBay category",
    responses=problems({**STAFF_ACCESS, **_OFF}, unsafe=False, validated=False),
)
async def list_categories(_: ListingEditor, marketplace: MarketplaceDep) -> CategoryMappingListOut:
    mappings = await marketplace.connection.category_map()
    return CategoryMappingListOut(items=[CategoryMappingOut.from_mapping(m) for m in mappings])


@router.put(
    "/categories",
    operation_id="setEbayCategories",
    summary="Replace the eBay categories of the shop's categories",
    responses=problems({**STAFF_ACCESS, **_OFF}),
)
async def set_categories(
    body: CategoryMappingListIn, _: EbayOwner, marketplace: MarketplaceDep
) -> CategoryMappingListOut:
    mappings = await marketplace.connection.set_category_map(
        {item.category_id: item.ebay_category_id for item in body.items}
    )
    return CategoryMappingListOut(items=[CategoryMappingOut.from_mapping(m) for m in mappings])


@router.get(
    "/listings",
    operation_id="listEbayListings",
    summary="Offers on eBay, the last changed first",
    responses=problems({**STAFF_ACCESS, **_OFF}, unsafe=False),
)
async def list_listings(
    _: ListingEditor,
    marketplace: MarketplaceDep,
    cursor: Annotated[str | None, Query(max_length=200)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> ListingPageOut:
    page = await marketplace.listings.page(cursor=cursor, limit=limit)
    return ListingPageOut.from_page(page, marketplace.mode)


@router.get(
    "/products/{product_id}/listings",
    operation_id="listProductEbayListings",
    summary="The product's offers on eBay, one per scale",
    responses=problems({**STAFF_ACCESS, **_OFF}, unsafe=False),
)
async def list_product_listings(
    product_id: UUID, _: ListingEditor, marketplace: MarketplaceDep
) -> ListingListOut:
    listings = await marketplace.listings.of_product(product_id)
    return ListingListOut(
        items=[ListingOut.from_listing(listing, marketplace.mode) for listing in listings]
    )


@router.put(
    "/products/{product_id}/listings/{scale_code}",
    operation_id="setProductEbayListing",
    summary="Offer the product in the scale on eBay, or take it down",
    description="The worker brings it up (or down) within a minute; or sync it right away.",
    responses=problems({**STAFF_ACCESS, **_OFF, 404: ["listing_not_found"]}),
)
async def set_product_listing(
    product_id: UUID,
    scale_code: Annotated[str, Path(max_length=8)],
    body: WantIn,
    _: ListingEditor,
    marketplace: MarketplaceDep,
) -> ListingOut:
    listing = await marketplace.listings.want(product_id, scale_code, wanted=body.wanted)
    return ListingOut.from_listing(listing, marketplace.mode)


@router.post(
    "/listings/{listing_id}/sync",
    operation_id="syncEbayListing",
    summary="Bring the listing on eBay up to date now",
    responses=problems(
        {
            **STAFF_ACCESS,
            404: ["listing_not_found"],
            409: [EBAY_OFF, "ebay_not_connected", "ebay_not_ready"],
            **EBAY_UNAVAILABLE,
        }
    ),
)
async def sync_listing(
    listing_id: UUID, _: ListingEditor, marketplace: MarketplaceDep
) -> ListingOut:
    listing = await marketplace.listings.sync(listing_id)
    return ListingOut.from_listing(listing, marketplace.mode)


@router.get(
    "/orders",
    operation_id="listEbayOrders",
    summary="The latest orders from eBay",
    responses=problems({**STAFF_ACCESS, **_OFF}, unsafe=False, validated=False),
)
async def list_orders(_: ListingEditor, marketplace: MarketplaceDep) -> MarketplaceOrderListOut:
    views = await marketplace.orders.recent()
    return MarketplaceOrderListOut(items=[MarketplaceOrderOut.from_view(v) for v in views])


@router.post(
    "/orders/fetch",
    operation_id="fetchEbayOrders",
    summary="Ask eBay for new orders now",
    responses=problems({**STAFF_ACCESS, **_OFF, **EBAY_UNAVAILABLE}, validated=False),
)
async def fetch_orders(_: ListingEditor, marketplace: MarketplaceDep) -> FetchOut:
    return FetchOut(received=await marketplace.orders.fetch())


@router.post(
    "/orders/{marketplace_order_id}/report-shipment",
    operation_id="reportEbayShipment",
    summary="Tell eBay again how the order was shipped",
    responses=problems(
        {**STAFF_ACCESS, **_OFF, 404: ["marketplace_order_not_found"], **EBAY_UNAVAILABLE}
    ),
)
async def report_shipment(
    marketplace_order_id: UUID, _: ListingEditor, marketplace: MarketplaceDep
) -> MarketplaceOrderOut:
    order = await marketplace.orders.report_again(marketplace_order_id)
    return MarketplaceOrderOut.from_view(OrderView(order=order, order_number=None))


@router.post(
    "/test-sales",
    status_code=status.HTTP_201_CREATED,
    operation_id="createEbayTestSale",
    summary="Buy on the built-in test marketplace, as an eBay buyer would",
    responses=problems(
        {**STAFF_ACCESS, 404: ["listing_not_found"], 409: [EBAY_OFF, "test_mode_only"]}
    ),
)
async def create_test_sale(
    body: TestSaleIn, _: ListingEditor, marketplace: MarketplaceDep
) -> TestSaleOut:
    external_id = await marketplace.orders.sell_test(sku=body.sku, quantity=body.quantity)
    return TestSaleOut(external_id=external_id)


@router.post(
    "/test-sales/{external_id}/cancel",
    status_code=status.HTTP_204_NO_CONTENT,
    operation_id="cancelEbayTestSale",
    summary="Cancel a test sale, as the buyer would on eBay",
    responses=problems(
        {
            **STAFF_ACCESS,
            404: ["marketplace_order_not_found"],
            409: [EBAY_OFF, "test_mode_only"],
        }
    ),
)
async def cancel_test_sale(external_id: str, _: ListingEditor, marketplace: MarketplaceDep) -> None:
    await marketplace.orders.cancel_test(external_id)


@router.get(
    "/account-deletion",
    operation_id="getEbayAccountDeletionSetup",
    summary="What eBay's developer account needs for notifications of closed accounts",
    responses=problems(STAFF_ACCESS, unsafe=False, validated=False),
)
async def get_account_deletion_setup(
    _: ListingEditor, deletions: AccountDeletionsDep
) -> AccountDeletionSetupOut:
    return AccountDeletionSetupOut(
        endpoint=deletions.endpoint,
        token_set=deletions.ready,
        checks_signatures=deletions.checks_signatures,
        test_buyer_name=deletions.test_buyer_name,
    )


@router.post(
    "/test-buyer/close-account",
    operation_id="closeEbayTestBuyerAccount",
    summary="The test buyer closes their eBay account; eBay's notification follows",
    responses=problems({**STAFF_ACCESS, 409: ["test_mode_only"]}, validated=False),
)
async def close_test_buyer_account(
    _: ListingEditor, deletions: AccountDeletionsDep
) -> TestAccountClosedOut:
    receipt = await deletions.close_test_account()
    return TestAccountClosedOut(erased_orders=receipt.erased_orders)


def _handoff(outcome: str, message: str) -> HTMLResponse:
    target = f"{_STELLWERK_PAGE}?ebay={outcome}"
    page = (
        '<!doctype html><html lang="de"><head><meta charset="utf-8">'
        f'<meta http-equiv="refresh" content="0;url={escape(target)}">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        "<title>eBay · Stellwerk</title></head>"
        '<body style="font-family:system-ui,sans-serif;background:#f6f7f9;color:#1c1f24;'
        'display:grid;place-items:center;min-height:100vh;margin:0">'
        f'<p>{escape(message)} <a href="{escape(target)}">Weiter zum Stellwerk</a></p>'
        "</body></html>"
    )
    return HTMLResponse(
        page,
        headers={
            "Cache-Control": "no-store",
            "Referrer-Policy": "no-referrer",
            "Content-Security-Policy": (
                "default-src 'none'; style-src 'unsafe-inline'; frame-ancestors 'none'"
            ),
        },
    )
