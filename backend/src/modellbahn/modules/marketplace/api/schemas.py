"""Request and response bodies of the marketplace API."""

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from modellbahn.modules.catalog.contracts.listings import ProductLabel
from modellbahn.modules.marketplace.application.connection import CategoryMapping
from modellbahn.modules.marketplace.application.listings import ListingPage, ListingView
from modellbahn.modules.marketplace.application.orders import OrderView
from modellbahn.modules.marketplace.application.ports import GatewayMode, Policies, PolicyOption
from modellbahn.modules.marketplace.domain.model import (
    MADE_TO_ORDER_QUANTITY_MAX,
    MARKUP_MAX_PERCENT,
    Blocker,
    ConnectionStatus,
    EbayAccount,
    Listing,
    ListingStatus,
    MarketplaceOrderStatus,
)

Cents = Annotated[int, Field(ge=0, examples=[8480])]
# Where eBay shows a listing, by mode (the test marketplace shows none).
_ITEM_URLS = {
    GatewayMode.SANDBOX: "https://www.sandbox.ebay.de/itm/",
    GatewayMode.PRODUCTION: "https://www.ebay.de/itm/",
}


class _Request(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EbayMode(StrEnum):
    OFF = "off"
    TEST = "test"
    SANDBOX = "sandbox"
    PRODUCTION = "production"


def item_url(mode: GatewayMode | None, external_id: str) -> str | None:
    base = _ITEM_URLS.get(mode) if mode is not None else None
    return f"{base}{external_id}" if base and external_id else None


# --- Account --------------------------------------------------------------------------


class EbayStatusOut(BaseModel):
    """The connection to eBay and how the shop sells there."""

    mode: EbayMode = Field(
        description="off: no eBay; test: the built-in test marketplace; sandbox or production."
    )
    status: ConnectionStatus
    seller_name: str = Field(examples=["adp-modelle"])
    connected_at: datetime | None
    consent_expires_at: datetime | None = Field(
        description="Until when eBay's consent holds; connect again before."
    )
    blockers: list[Blocker] = Field(description="What keeps offers from going up.")
    fulfillment_policy_id: str
    payment_policy_id: str
    return_policy_id: str
    location_ready: bool
    price_markup_percent: int = Field(ge=0, le=MARKUP_MAX_PERCENT)
    made_to_order_quantity: int = Field(ge=1, le=MADE_TO_ORDER_QUANTITY_MAX)
    orders_checked_until: datetime | None

    @classmethod
    def off(cls) -> Self:
        return cls(
            mode=EbayMode.OFF,
            status=ConnectionStatus.DISCONNECTED,
            seller_name="",
            connected_at=None,
            consent_expires_at=None,
            blockers=[Blocker.NOT_CONNECTED],
            fulfillment_policy_id="",
            payment_policy_id="",
            return_policy_id="",
            location_ready=False,
            price_markup_percent=0,
            made_to_order_quantity=1,
            orders_checked_until=None,
        )

    @classmethod
    def from_account(cls, account: EbayAccount, mode: GatewayMode) -> Self:
        return cls(
            mode=EbayMode(mode.value),
            status=account.status,
            seller_name=account.seller_name,
            connected_at=account.connected_at,
            consent_expires_at=account.refresh_expires_at,
            blockers=account.blockers,
            fulfillment_policy_id=account.fulfillment_policy_id,
            payment_policy_id=account.payment_policy_id,
            return_policy_id=account.return_policy_id,
            location_ready=account.location_ready,
            price_markup_percent=account.price_markup_percent,
            made_to_order_quantity=account.made_to_order_quantity,
            orders_checked_until=account.orders_checked_until,
        )


class ConnectOut(BaseModel):
    authorize_url: str = Field(description="eBay's consent page; open it in the same tab.")


class SettingsIn(_Request):
    """What changes; a missing field keeps its value, an empty policy id clears it."""

    fulfillment_policy_id: str | None = Field(default=None, max_length=40)
    payment_policy_id: str | None = Field(default=None, max_length=40)
    return_policy_id: str | None = Field(default=None, max_length=40)
    price_markup_percent: int | None = Field(default=None, ge=0, le=MARKUP_MAX_PERCENT)
    made_to_order_quantity: int | None = Field(
        default=None,
        ge=1,
        le=MADE_TO_ORDER_QUANTITY_MAX,
        description="How many pieces of a model made to order eBay may sell at once.",
    )


class PolicyOptionOut(BaseModel):
    id: str
    name: str

    @classmethod
    def from_option(cls, option: PolicyOption) -> Self:
        return cls(id=option.id, name=option.name)


class PoliciesOut(BaseModel):
    """The business policies of the eBay account, to choose from."""

    fulfillment: list[PolicyOptionOut]
    payment: list[PolicyOptionOut]
    returns: list[PolicyOptionOut]

    @classmethod
    def from_policies(cls, policies: Policies) -> Self:
        return cls(
            fulfillment=[PolicyOptionOut.from_option(o) for o in policies.fulfillment],
            payment=[PolicyOptionOut.from_option(o) for o in policies.payment],
            returns=[PolicyOptionOut.from_option(o) for o in policies.returns],
        )


class CategoryMappingOut(BaseModel):
    category_id: UUID
    path: str = Field(examples=["Straßenfahrzeuge / LKW"])
    ebay_category_id: str = Field(examples=["180250"], description="Empty: none chosen.")

    @classmethod
    def from_mapping(cls, mapping: CategoryMapping) -> Self:
        return cls(
            category_id=mapping.category_id,
            path=mapping.path,
            ebay_category_id=mapping.ebay_category_id,
        )


class CategoryMappingListOut(BaseModel):
    items: list[CategoryMappingOut]


class CategoryMappingIn(_Request):
    category_id: UUID
    ebay_category_id: str = Field(max_length=10, examples=["180250"])


class CategoryMappingListIn(_Request):
    """The whole mapping; categories left out (or empty) have none."""

    items: list[CategoryMappingIn] = Field(max_length=500)


# --- Listings -------------------------------------------------------------------------


class ListingItemOut(BaseModel):
    sku: str
    quantity: int = Field(description="What eBay may sell at once, as last told.")
    price_cents: Cents


class ListingProductOut(BaseModel):
    product_id: UUID
    number: int
    slug: str
    name: str

    @classmethod
    def from_label(cls, label: ProductLabel) -> Self:
        return cls(
            product_id=label.product_id, number=label.number, slug=label.slug, name=label.name
        )


class ListingOut(BaseModel):
    """A product in one scale as an offer on eBay."""

    id: UUID
    product_id: UUID
    scale_code: str
    group_key: str = Field(examples=["MB-000042-H0"])
    wanted: bool = Field(description="The shop wants it on eBay.")
    status: ListingStatus
    external_id: str = Field(description="eBay's listing number, once it went up.")
    url: str | None = Field(description="The listing on eBay (none on the test marketplace).")
    needs_sync: bool
    error_code: str | None
    error_message: str
    synced_at: datetime | None
    updated_at: datetime
    items: list[ListingItemOut]
    product: ListingProductOut | None = None

    @classmethod
    def from_listing(
        cls, listing: Listing, mode: GatewayMode, product: ProductLabel | None = None
    ) -> Self:
        return cls(
            id=listing.id,
            product_id=listing.product_id,
            scale_code=listing.scale_code,
            group_key=listing.group_key,
            wanted=listing.wanted,
            status=listing.status,
            external_id=listing.external_id,
            url=item_url(mode, listing.external_id) if listing.is_up else None,
            needs_sync=listing.needs_sync,
            error_code=listing.error_code,
            error_message=listing.error_message,
            synced_at=listing.synced_at,
            updated_at=listing.updated_at,
            items=[
                ListingItemOut(sku=item.sku, quantity=item.quantity, price_cents=item.price_cents)
                for item in listing.items
            ],
            product=ListingProductOut.from_label(product) if product is not None else None,
        )

    @classmethod
    def from_view(cls, view: ListingView, mode: GatewayMode) -> Self:
        return cls.from_listing(view.listing, mode, view.product)


class ListingListOut(BaseModel):
    items: list[ListingOut]


class ListingPageOut(BaseModel):
    items: list[ListingOut]
    next_cursor: str | None

    @classmethod
    def from_page(cls, page: ListingPage, mode: GatewayMode) -> Self:
        return cls(
            items=[ListingOut.from_view(view, mode) for view in page.items],
            next_cursor=page.next_cursor,
        )


class WantIn(_Request):
    wanted: bool = Field(description="True: offer it on eBay; false: take it down.")


# --- Orders ---------------------------------------------------------------------------


class MarketplaceOrderLineOut(BaseModel):
    sku: str
    title: str
    quantity: int
    unit_price_cents: Cents
    known: bool = Field(description="The article is one of the shop's variants.")


class MarketplaceOrderOut(BaseModel):
    """An order as eBay reported it, with the shop's order it became."""

    id: UUID
    external_id: str = Field(examples=["12-34567-89012"])
    order_id: UUID
    order_number: str | None = Field(description="The shop's order, once the sales took it.")
    status: MarketplaceOrderStatus
    buyer_name: str
    recipient: str
    city: str
    country_code: str
    shipping_cents: Cents
    total_cents: Cents
    paid_at: datetime
    received_at: datetime
    shipped_reported_at: datetime | None
    problem: str = Field(description="Why it was rejected, or why reporting the shipment failed.")
    lines: list[MarketplaceOrderLineOut]

    @classmethod
    def from_view(cls, view: OrderView) -> Self:
        order = view.order
        return cls(
            id=order.id,
            external_id=order.external_id,
            order_id=order.order_id,
            order_number=view.order_number,
            status=order.status,
            buyer_name=order.buyer_name,
            recipient=order.recipient,
            city=order.city,
            country_code=order.country_code,
            shipping_cents=order.shipping_cents,
            total_cents=order.total_cents,
            paid_at=order.paid_at,
            received_at=order.received_at,
            shipped_reported_at=order.shipped_reported_at,
            problem=order.problem,
            lines=[
                MarketplaceOrderLineOut(
                    sku=line.sku,
                    title=line.title,
                    quantity=line.quantity,
                    unit_price_cents=line.unit_price_cents,
                    known=line.variant_id is not None,
                )
                for line in order.lines
            ],
        )


class MarketplaceOrderListOut(BaseModel):
    items: list[MarketplaceOrderOut]


class FetchOut(BaseModel):
    received: int = Field(description="New orders taken over.")


class TestSaleIn(_Request):
    sku: str = Field(min_length=1, max_length=40, examples=["MB-000042-H0-F"])
    quantity: int = Field(default=1, ge=1, le=99)


class TestSaleOut(BaseModel):
    external_id: str = Field(examples=["T7-04213-88351"])
