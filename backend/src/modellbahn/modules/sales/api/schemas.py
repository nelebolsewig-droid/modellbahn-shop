"""Request and response bodies of the sales API (snake_case JSON).

Amounts are cents (gross, including 19 % VAT).
"""

from datetime import datetime
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from modellbahn.modules.inventory.contracts.availability import Availability
from modellbahn.modules.media.contracts.images import ImageView, RenditionFormat
from modellbahn.modules.sales.application.cart import CartItem, CartView
from modellbahn.modules.sales.application.checkout import AddressInput
from modellbahn.modules.sales.application.common import OrderDetails, OrderPage
from modellbahn.modules.sales.domain.model import (
    CANCEL_NOTE_MAX_LENGTH,
    CARRIER_MAX_LENGTH,
    LINE_MAX_QUANTITY,
    SHIPPING_ZONES,
    TRACKING_NUMBER_MAX_LENGTH,
    CancelReason,
    CustomerAddress,
    Order,
    OrderLine,
    OrderStatus,
    Payment,
    PaymentStatus,
    PostalAddress,
    ShippingZone,
)

Cents = Annotated[int, Field(ge=0, examples=[8480])]


class _Request(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --- Shared ---------------------------------------------------------------------------


class LineImageRenditionOut(BaseModel):
    name: str = Field(examples=["thumb"])
    format: RenditionFormat
    width: int
    height: int
    url: str


class LineImageOut(BaseModel):
    """The photo of a cart or order line: placeholder, dominant colour, rendered sizes."""

    asset_id: UUID
    width: int
    height: int
    dominant_color: str = Field(examples=["#c8c8be"])
    lqip: str
    renditions: list[LineImageRenditionOut]

    @classmethod
    def from_view(cls, view: ImageView | None) -> Self | None:
        if view is None or view.width is None or view.height is None or view.lqip is None:
            return None
        return cls(
            asset_id=view.asset_id,
            width=view.width,
            height=view.height,
            dominant_color=view.dominant_color or "#ecece8",
            lqip=view.lqip,
            renditions=[
                LineImageRenditionOut(
                    name=r.name, format=r.format, width=r.width, height=r.height, url=r.url
                )
                for r in view.renditions
            ],
        )


class ShippingCountryOut(BaseModel):
    """A country the shop ships to, with its flat rate and the order value that ships free."""

    code: str = Field(examples=["DE"])
    name: str = Field(examples=["Deutschland"])
    rate_cents: Cents
    free_from_cents: Cents | None = Field(description="Null: shipping is never free.")

    @classmethod
    def from_zone(cls, zone: ShippingZone) -> Self:
        return cls(
            code=zone.country_code,
            name=zone.name,
            rate_cents=zone.rate_cents,
            free_from_cents=zone.free_from_cents,
        )


class TotalsOut(BaseModel):
    subtotal_cents: Cents
    shipping_cents: Cents
    total_cents: Cents
    tax_cents: Cents = Field(description="The 19 % VAT contained in the total.")


class AddressIn(_Request):
    recipient: str = Field(max_length=200, examples=["Erika Mustermann"])
    street: str = Field(max_length=200, examples=["Bahnhofstraße 12"])
    postal_code: str = Field(max_length=20, examples=["38707"])
    city: str = Field(max_length=200, examples=["Altenau"])
    country_code: str = Field(max_length=2, examples=["DE"])

    def to_input(self) -> AddressInput:
        return AddressInput(
            recipient=self.recipient,
            street=self.street,
            postal_code=self.postal_code,
            city=self.city,
            country_code=self.country_code,
        )


class AddressOut(BaseModel):
    recipient: str
    street: str
    postal_code: str
    city: str
    country_code: str
    country_name: str = Field(examples=["Deutschland"])

    @classmethod
    def from_address(cls, address: PostalAddress) -> Self:
        return cls(
            recipient=address.recipient,
            street=address.street,
            postal_code=address.postal_code,
            city=address.city,
            country_code=address.country_code,
            country_name=address.zone.name,
        )


# --- Cart -----------------------------------------------------------------------------


class CartLineOut(BaseModel):
    variant_id: UUID
    product_slug: str
    product_name: str
    scale_code: str
    scale_name: str
    finish_code: str
    finish_name: str
    color: str = Field(description="Empty for a kit or a finished model in one colour.")
    sku: str
    quantity: int
    unit_price_cents: Cents
    compare_at_price_cents: Cents | None
    line_total_cents: Cents
    available: bool = Field(
        description="False if the variant is no longer for sale, or not deliverable in "
        "this quantity (not enough in stock and not made to order)."
    )
    availability: Availability = Field(
        description="`in_stock`: ships at once; `made_to_order`: printed for the customer; "
        "`unavailable`: cannot be ordered like this."
    )
    free_units: int = Field(description="Units of the variant on the shelves right now.")
    lead_time_min_weeks: int | None = Field(description="Set for variants made to order.")
    lead_time_max_weeks: int | None
    image: LineImageOut | None

    @classmethod
    def from_item(cls, item: CartItem) -> Self:
        variant = item.variant
        lead_time = variant.lead_time_weeks if variant.allow_backorder else None
        return cls(
            variant_id=variant.variant_id,
            product_slug=variant.product_slug,
            product_name=variant.product_name,
            scale_code=variant.scale_code,
            scale_name=variant.scale_name,
            finish_code=variant.finish_code,
            finish_name=variant.finish_name,
            color=variant.color,
            sku=variant.sku,
            quantity=item.quantity,
            unit_price_cents=variant.price_cents,
            compare_at_price_cents=variant.compare_at_price_cents,
            line_total_cents=item.line_total_cents,
            available=item.available,
            availability=item.availability,
            free_units=item.free_units,
            lead_time_min_weeks=lead_time[0] if lead_time else None,
            lead_time_max_weeks=lead_time[1] if lead_time else None,
            image=LineImageOut.from_view(item.image),
        )


class CartOut(BaseModel):
    """The cart at today's prices; shipping is that to Germany until an address is known."""

    lines: list[CartLineOut]
    item_count: int = Field(description="Pieces that can be ordered.")
    totals: TotalsOut
    shipping_country: ShippingCountryOut
    ready_for_checkout: bool
    countries: list[ShippingCountryOut] = Field(description="Every country the shop ships to.")

    @classmethod
    def from_view(cls, view: CartView) -> Self:
        totals = view.totals
        return cls(
            lines=[CartLineOut.from_item(item) for item in view.items],
            item_count=view.item_count,
            totals=TotalsOut(
                subtotal_cents=totals.subtotal_cents,
                shipping_cents=totals.shipping_cents,
                total_cents=totals.total_cents,
                tax_cents=totals.tax_cents,
            ),
            shipping_country=ShippingCountryOut.from_zone(view.shipping_zone),
            ready_for_checkout=view.ready_for_checkout,
            countries=[ShippingCountryOut.from_zone(zone) for zone in SHIPPING_ZONES.values()],
        )


class CartLineIn(_Request):
    quantity: int = Field(ge=0, le=LINE_MAX_QUANTITY, description="0 takes the line out.")


# --- Checkout and orders --------------------------------------------------------------


class CheckoutIn(_Request):
    """What the customer confirmed. Guests send ``email`` and ``address``; customers may
    send ``address_id`` from their book instead, or keep a new address (``save_address``)."""

    expected_total_cents: Cents = Field(
        description="The total shown on the review page; a different total refuses the order."
    )
    email: str | None = Field(default=None, max_length=254)
    address: AddressIn | None = None
    address_id: UUID | None = None
    save_address: bool = False


class PaymentIn(_Request):
    method: Literal["succeeds", "declined", "fails"] = Field(
        description="Test payment: the outcome the mock provider simulates."
    )


class OrderLineOut(BaseModel):
    variant_id: UUID
    product_slug: str
    sku: str
    title: str = Field(examples=["Stellwerk Altenau · H0 · bemalt"])
    scale_code: str
    finish_code: str
    unit_price_cents: Cents
    quantity: int
    line_total_cents: Cents
    image: LineImageOut | None

    @classmethod
    def from_line(cls, line: OrderLine, images: dict[UUID, ImageView]) -> Self:
        image = images.get(line.image_asset_id) if line.image_asset_id else None
        return cls(
            variant_id=line.variant_id,
            product_slug=line.product_slug,
            sku=line.sku,
            title=line.title,
            scale_code=line.scale_code,
            finish_code=line.finish_code,
            unit_price_cents=line.unit_price_cents,
            quantity=line.quantity,
            line_total_cents=line.line_total_cents,
            image=LineImageOut.from_view(image),
        )


class PaymentOut(BaseModel):
    status: PaymentStatus
    amount_cents: Cents
    provider: str = Field(examples=["mock"])
    failure_code: str | None = Field(examples=["declined"])
    created_at: datetime

    @classmethod
    def from_payment(cls, payment: Payment) -> Self:
        return cls(
            status=payment.status,
            amount_cents=payment.amount_cents,
            provider=payment.provider,
            failure_code=payment.failure_code,
            created_at=payment.created_at,
        )


class OrderOut(BaseModel):
    """An order as its customer sees it. ``public_token`` is the key of its status page."""

    number: str = Field(examples=["MB-2026-00042"])
    public_token: str
    status: OrderStatus
    email: str
    shipping_address: AddressOut
    lines: list[OrderLineOut]
    totals: TotalsOut
    payments: list[PaymentOut]
    placed_at: datetime
    paid_at: datetime | None
    shipped_at: datetime | None
    cancelled_at: datetime | None
    cancel_reason: CancelReason | None
    carrier: str
    tracking_number: str
    payment_due_at: datetime | None = Field(
        description="Until when a pending order can be paid; afterwards it is cancelled."
    )

    @classmethod
    def from_details(cls, details: OrderDetails) -> Self:
        order = details.order
        return cls(
            number=order.number,
            public_token=order.public_token,
            status=order.status,
            email=order.email,
            shipping_address=AddressOut.from_address(order.shipping_address),
            lines=[OrderLineOut.from_line(line, details.images) for line in order.lines],
            totals=_totals(order),
            payments=[PaymentOut.from_payment(p) for p in order.payments],
            placed_at=order.placed_at,
            paid_at=order.paid_at,
            shipped_at=order.shipped_at,
            cancelled_at=order.cancelled_at,
            cancel_reason=order.cancel_reason,
            carrier=order.carrier,
            tracking_number=order.tracking_number,
            payment_due_at=order.payment_due_at,
        )


def _totals(order: Order) -> TotalsOut:
    return TotalsOut(
        subtotal_cents=order.subtotal_cents,
        shipping_cents=order.shipping_cents,
        total_cents=order.total_cents,
        tax_cents=order.tax_cents,
    )


class OrderSummaryOut(BaseModel):
    """An order in a list."""

    id: UUID
    number: str
    status: OrderStatus
    placed_at: datetime
    item_count: int
    total_cents: Cents
    first_line_title: str
    recipient: str
    guest: bool = Field(description="Placed without an account (and not adopted yet).")

    @classmethod
    def from_order(cls, order: Order) -> Self:
        return cls(
            id=order.id,
            number=order.number,
            status=order.status,
            placed_at=order.placed_at,
            item_count=order.item_count,
            total_cents=order.total_cents,
            first_line_title=order.lines[0].title if order.lines else "",
            recipient=order.shipping_address.recipient,
            guest=order.is_guest_order,
        )


class OrderPageOut(BaseModel):
    items: list[OrderSummaryOut]
    next_cursor: str | None

    @classmethod
    def from_page(cls, page: OrderPage) -> Self:
        return cls(
            items=[OrderSummaryOut.from_order(order) for order in page.items],
            next_cursor=page.next_cursor,
        )


class AdminOrderOut(OrderOut):
    """An order in the admin area: also who ordered and the cancellation note."""

    id: UUID
    customer_account_id: UUID | None
    cancel_note: str

    @classmethod
    def from_details(cls, details: OrderDetails) -> Self:
        base = OrderOut.from_details(details).model_dump()
        order = details.order
        return cls(
            **base,
            id=order.id,
            customer_account_id=order.customer_account_id,
            cancel_note=order.cancel_note,
        )


class ShipIn(_Request):
    carrier: str = Field(default="", max_length=CARRIER_MAX_LENGTH, examples=["DHL"])
    tracking_number: str = Field(default="", max_length=TRACKING_NUMBER_MAX_LENGTH)


class CancelIn(_Request):
    note: str = Field(default="", max_length=CANCEL_NOTE_MAX_LENGTH)


# --- Address book ---------------------------------------------------------------------


class CustomerAddressOut(AddressOut):
    id: UUID
    label: str = Field(examples=["Zuhause"])
    is_default: bool

    @classmethod
    def from_entry(cls, entry: CustomerAddress) -> Self:
        return cls(
            **AddressOut.from_address(entry.address).model_dump(),
            id=entry.id,
            label=entry.label,
            is_default=entry.is_default,
        )


class CustomerAddressIn(AddressIn):
    label: str = Field(default="", max_length=100)
    is_default: bool = False


class CustomerAddressPatchIn(_Request):
    """Only the fields sent are changed; ``is_default: true`` makes the entry the default."""

    label: str | None = Field(default=None, max_length=100)
    address: AddressIn | None = None
    is_default: bool = False
