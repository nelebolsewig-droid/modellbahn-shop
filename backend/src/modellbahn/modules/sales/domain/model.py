"""The sales model: carts, orders with their payments, and the customers' address books.

A *cart* lives on the server and holds variants with quantities, nothing else: prices
come from the catalogue whenever the cart is read. Checking out turns it into an
*order*, which freezes article number, title and price of every line and the shipping
address, because the catalogue keeps changing after the purchase. An order waits for
its *payment*, is then shipped, or is cancelled (a payment that came in is refunded).

Plain dataclasses without any framework, mapped imperatively by the infrastructure.
Every method that depends on time takes ``now``.
"""

import hashlib
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Final
from uuid import NAMESPACE_URL, UUID, uuid5

from modellbahn.modules.sales.domain.errors import (
    AddressBookFullError,
    CartFullError,
    InvalidFieldError,
    InvalidOrderStateError,
    OrderNotPayableError,
)
from modellbahn.modules.sales.domain.events import (
    OrderCancelled,
    OrderPaid,
    OrderPlaced,
    OrderShipped,
)
from modellbahn.platform.events import DomainEvent
from modellbahn.platform.ids import new_id

CART_LIFETIME: Final = timedelta(days=30)
CART_MAX_LINES: Final = 50
LINE_MAX_QUANTITY: Final = 99
PAYMENT_TIMEOUT: Final = timedelta(hours=24)
ADDRESS_BOOK_MAX_SIZE: Final = 20
VAT_PERCENT: Final = 19
EMAIL_MAX_LENGTH: Final = 254
CANCEL_NOTE_MAX_LENGTH: Final = 300
TRACKING_NUMBER_MAX_LENGTH: Final = 40
CARRIER_MAX_LENGTH: Final = 40
EXTERNAL_REF_MAX_LENGTH: Final = 60
_EMAIL: Final = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


# --- Money ----------------------------------------------------------------------------


def included_vat(gross_cents: int) -> int:
    """The VAT contained in a gross amount at 19 %, rounded half up to the cent."""
    if gross_cents < 0:
        msg = "amounts are never negative"
        raise ValueError(msg)
    # round(gross * 19 / 119) with integers, half up.
    return (2 * gross_cents * VAT_PERCENT + 100 + VAT_PERCENT) // (2 * (100 + VAT_PERCENT))


@dataclass(frozen=True, slots=True)
class ShippingZone:
    """A country the shop ships to, with its flat rate and, if any, the order value that
    ships free."""

    country_code: str
    name: str
    rate_cents: int
    postal_code: re.Pattern[str]
    free_from_cents: int | None = None

    def cost(self, subtotal_cents: int) -> int:
        """Shipping for goods worth ``subtotal_cents``; nothing to ship costs nothing."""
        if subtotal_cents == 0:
            return 0
        if self.free_from_cents is not None and subtotal_cents >= self.free_from_cents:
            return 0
        return self.rate_cents


DOMESTIC_RATE_CENTS: Final = 590
EU_RATE_CENTS: Final = 1690

# The other member states of the EU, by German name, with the shape of their postal
# codes (upper case, a space where people write one, the country prefix optional).
_EU_COUNTRIES: Final = (
    ("BE", "Belgien", r"\d{4}"),
    ("BG", "Bulgarien", r"\d{4}"),
    ("DK", "Dänemark", r"\d{4}"),
    ("EE", "Estland", r"\d{5}"),
    ("FI", "Finnland", r"\d{5}"),
    ("FR", "Frankreich", r"\d{5}"),
    ("GR", "Griechenland", r"\d{3} ?\d{2}"),
    ("IE", "Irland", r"(?:[AC-FHKNPRTV-Y]\d{2}|D6W) ?[0-9AC-FHKNPRTV-Y]{4}"),
    ("IT", "Italien", r"\d{5}"),
    ("HR", "Kroatien", r"\d{5}"),
    ("LV", "Lettland", r"(?:LV-)?\d{4}"),
    ("LT", "Litauen", r"(?:LT-)?\d{5}"),
    ("LU", "Luxemburg", r"(?:L-)?\d{4}"),
    ("MT", "Malta", r"[A-Z]{3} ?\d{2,4}"),
    ("NL", "Niederlande", r"\d{4} ?[A-Z]{2}"),
    ("AT", "Österreich", r"\d{4}"),
    ("PL", "Polen", r"\d{2}-\d{3}"),
    ("PT", "Portugal", r"\d{4}-\d{3}"),
    ("RO", "Rumänien", r"\d{6}"),
    ("SE", "Schweden", r"\d{3} ?\d{2}"),
    ("SK", "Slowakei", r"\d{3} ?\d{2}"),
    ("SI", "Slowenien", r"(?:SI-)?\d{4}"),
    ("ES", "Spanien", r"\d{5}"),
    ("CZ", "Tschechien", r"\d{3} ?\d{2}"),
    ("HU", "Ungarn", r"\d{4}"),
    ("CY", "Zypern", r"\d{4}"),
)

# Germany first, then the rest of the EU; no order ships free (owner, 28.10.2026).
SHIPPING_ZONES: Final = {
    zone.country_code: zone
    for zone in (
        ShippingZone("DE", "Deutschland", DOMESTIC_RATE_CENTS, re.compile(r"^[0-9]{5}$")),
        *(
            ShippingZone(code, name, EU_RATE_CENTS, re.compile(f"^{pattern}$"))
            for code, name, pattern in _EU_COUNTRIES
        ),
    )
}
DEFAULT_COUNTRY: Final = "DE"


def shipping_zone(country_code: str) -> ShippingZone:
    zone = SHIPPING_ZONES.get(country_code)
    if zone is None:
        raise InvalidFieldError("country_code", "not_shipped", "the shop does not ship there")
    return zone


@dataclass(frozen=True, slots=True)
class Totals:
    """What an order costs: goods, shipping and the VAT contained in the sum."""

    subtotal_cents: int
    shipping_cents: int
    total_cents: int
    tax_cents: int

    @classmethod
    def of(cls, subtotal_cents: int, zone: ShippingZone) -> "Totals":
        shipping = zone.cost(subtotal_cents)
        total = subtotal_cents + shipping
        return cls(subtotal_cents, shipping, total, included_vat(total))


# --- Addresses ------------------------------------------------------------------------


def _text(value: str, field_name: str, max_length: int, *, required: bool = True) -> str:
    cleaned = " ".join(value.split())
    if required and not cleaned:
        raise InvalidFieldError(field_name, "required", "must not be empty")
    if len(cleaned) > max_length:
        raise InvalidFieldError(field_name, "too_long", f"at most {max_length} characters")
    return cleaned


def normalize_email(value: str) -> str:
    """Trimmed and checked; the domain part is lower-cased, the local part kept as typed."""
    cleaned = value.strip()
    if len(cleaned) > EMAIL_MAX_LENGTH or not _EMAIL.match(cleaned):
        raise InvalidFieldError("email", "invalid", "not a valid e-mail address")
    local, _, domain = cleaned.rpartition("@")
    return f"{local}@{domain.lower()}"


@dataclass(frozen=True, slots=True)
class PostalAddress:
    """Where a parcel goes. Only countries the shop ships to are valid."""

    recipient: str
    street: str
    postal_code: str
    city: str
    country_code: str

    @classmethod
    def create(
        cls, *, recipient: str, street: str, postal_code: str, city: str, country_code: str
    ) -> "PostalAddress":
        country = country_code.strip().upper()
        zone = shipping_zone(country)
        # "1012 ab" is written "1012 AB": upper case, single spaces.
        code = " ".join(postal_code.upper().split())
        if not zone.postal_code.match(code):
            raise InvalidFieldError("postal_code", "invalid", f"not a postal code in {country}")
        return cls(
            recipient=_text(recipient, "recipient", 80),
            street=_text(street, "street", 100),
            postal_code=code,
            city=_text(city, "city", 60),
            country_code=country,
        )

    @property
    def zone(self) -> ShippingZone:
        return shipping_zone(self.country_code)

    def lines(self) -> list[str]:
        """The address as printed on a parcel."""
        return [
            self.recipient,
            self.street,
            f"{self.postal_code} {self.city}",
            self.zone.name,
        ]


@dataclass(eq=False)
class CustomerAddress:
    """An entry in a customer's address book; one of them may be the default."""

    id: UUID
    account_id: UUID
    label: str
    address: PostalAddress
    is_default: bool
    created_at: datetime
    updated_at: datetime

    @classmethod
    def create(
        cls,
        *,
        account_id: UUID,
        label: str,
        address: PostalAddress,
        existing: Sequence["CustomerAddress"],
        now: datetime,
    ) -> "CustomerAddress":
        """A new entry; the first one of a book becomes its default."""
        if len(existing) >= ADDRESS_BOOK_MAX_SIZE:
            raise AddressBookFullError
        return cls(
            id=new_id(),
            account_id=account_id,
            label=_text(label, "label", 40, required=False),
            address=address,
            is_default=not existing,
            created_at=now,
            updated_at=now,
        )

    def change(self, *, label: str, address: PostalAddress, now: datetime) -> None:
        self.label = _text(label, "label", 40, required=False)
        self.address = address
        self.updated_at = now


def make_default(book: Sequence[CustomerAddress], address_id: UUID, now: datetime) -> None:
    """Make one entry of the book the default; the previous default stops being one."""
    for entry in book:
        wanted = entry.id == address_id
        if entry.is_default != wanted:
            entry.is_default = wanted
            entry.updated_at = now


def after_removal(book: Sequence[CustomerAddress], now: datetime) -> None:
    """Keep a default after an entry was removed: the oldest remaining one takes over."""
    if book and not any(entry.is_default for entry in book):
        oldest = min(book, key=lambda entry: entry.created_at)
        make_default(book, oldest.id, now)


# --- Cart -----------------------------------------------------------------------------


@dataclass(eq=False)
class CartLine:
    cart_id: UUID
    variant_id: UUID
    quantity: int
    added_at: datetime


@dataclass(eq=False)
class Cart:
    """Variants and quantities a visitor wants; it expires 30 days after its last change."""

    id: UUID
    created_at: datetime
    updated_at: datetime
    expires_at: datetime
    lines: list[CartLine] = field(default_factory=list)

    @classmethod
    def start(cls, now: datetime) -> "Cart":
        return cls(id=new_id(), created_at=now, updated_at=now, expires_at=now + CART_LIFETIME)

    def is_expired(self, now: datetime) -> bool:
        return now >= self.expires_at

    def line_for(self, variant_id: UUID) -> CartLine | None:
        return next((line for line in self.lines if line.variant_id == variant_id), None)

    def set_quantity(self, variant_id: UUID, quantity: int, now: datetime) -> None:
        """Put ``quantity`` pieces of a variant in the cart (0 takes it out)."""
        if not 0 <= quantity <= LINE_MAX_QUANTITY:
            raise InvalidFieldError(
                "quantity", "out_of_range", f"between 0 and {LINE_MAX_QUANTITY}"
            )
        line = self.line_for(variant_id)
        if quantity == 0:
            if line is not None:
                self.lines.remove(line)
        elif line is not None:
            line.quantity = quantity
        else:
            if len(self.lines) >= CART_MAX_LINES:
                raise CartFullError
            self.lines.append(
                CartLine(cart_id=self.id, variant_id=variant_id, quantity=quantity, added_at=now)
            )
        self._touch(now)

    def clear(self, now: datetime) -> None:
        self.lines.clear()
        self._touch(now)

    def _touch(self, now: datetime) -> None:
        self.updated_at = now
        self.expires_at = now + CART_LIFETIME


# --- Orders ---------------------------------------------------------------------------


class OrderStatus(StrEnum):
    PENDING_PAYMENT = "pending_payment"
    PAID = "paid"
    SHIPPED = "shipped"
    CANCELLED = "cancelled"


class CancelReason(StrEnum):
    PAYMENT_TIMEOUT = "payment_timeout"
    BY_SHOP = "by_shop"
    BY_MARKETPLACE = "by_marketplace"
    """The buyer or the marketplace cancelled; the marketplace refunds the payment."""


class SalesChannel(StrEnum):
    """Where an order came from. A marketplace order arrives paid; its buyer hears from there."""

    SHOP = "shop"
    EBAY = "ebay"


class PaymentStatus(StrEnum):
    CAPTURED = "captured"
    FAILED = "failed"
    REFUNDED = "refunded"


def order_number(year: int, serial: int) -> str:
    """Readable order number, e.g. ``MB-2026-00042``."""
    return f"MB-{year}-{serial:05d}"


@dataclass(frozen=True, slots=True)
class PricedItem:
    """A cart line priced from the catalogue at checkout: what the order line freezes."""

    variant_id: UUID
    product_slug: str
    sku: str
    title: str
    scale_code: str
    finish_code: str
    unit_price_cents: int
    quantity: int
    image_asset_id: UUID | None


@dataclass(eq=False)
class OrderLine:
    id: UUID
    order_id: UUID
    position: int
    variant_id: UUID
    product_slug: str
    sku: str
    title: str
    scale_code: str
    finish_code: str
    unit_price_cents: int
    quantity: int
    line_total_cents: int
    image_asset_id: UUID | None


@dataclass(frozen=True, slots=True)
class ChargeResult:
    """What the payment provider answered: captured or declined, with its reference."""

    captured: bool
    provider: str
    provider_ref: str
    failure_code: str | None = None


@dataclass(eq=False)
class Payment:
    id: UUID
    order_id: UUID
    provider: str
    provider_ref: str
    status: PaymentStatus
    amount_cents: int
    idempotency_key: UUID
    request_fingerprint: str
    failure_code: str | None
    created_at: datetime
    updated_at: datetime

    def refund(self, now: datetime) -> None:
        if self.status is not PaymentStatus.CAPTURED:
            msg = "only a captured payment can be refunded"
            raise InvalidOrderStateError(msg)
        self.status = PaymentStatus.REFUNDED
        self.updated_at = now


@dataclass(eq=False)
class Order:
    """A customer's binding order: frozen lines, address and totals, then payment and dispatch.

    ``customer_account_id`` is empty for a guest order; such an order is adopted by the
    customer account whose verified e-mail address it was placed with.
    """

    id: UUID
    number: str
    public_token: str
    status: OrderStatus
    customer_account_id: UUID | None
    email: str
    shipping_address: PostalAddress
    subtotal_cents: int
    shipping_cents: int
    total_cents: int
    tax_cents: int
    checkout_key: UUID
    checkout_fingerprint: str
    placed_at: datetime
    updated_at: datetime
    paid_at: datetime | None = None
    shipped_at: datetime | None = None
    cancelled_at: datetime | None = None
    cancel_reason: CancelReason | None = None
    cancel_note: str = ""
    carrier: str = ""
    tracking_number: str = ""
    channel: SalesChannel = SalesChannel.SHOP
    external_ref: str | None = None
    """The marketplace's order number (empty for the shop's own orders)."""
    lines: list[OrderLine] = field(default_factory=list)
    payments: list[Payment] = field(default_factory=list)

    @classmethod
    def place(
        cls,
        *,
        number: str,
        public_token: str,
        items: Sequence[PricedItem],
        email: str,
        address: PostalAddress,
        customer_account_id: UUID | None,
        checkout_key: UUID,
        checkout_fingerprint: str,
        now: datetime,
    ) -> tuple["Order", OrderPlaced]:
        if not items:
            msg = "an order needs at least one line"
            raise ValueError(msg)
        order_id = new_id()
        lines = [
            OrderLine(
                id=new_id(),
                order_id=order_id,
                position=position,
                variant_id=item.variant_id,
                product_slug=item.product_slug,
                sku=item.sku,
                title=item.title,
                scale_code=item.scale_code,
                finish_code=item.finish_code,
                unit_price_cents=item.unit_price_cents,
                quantity=item.quantity,
                line_total_cents=item.unit_price_cents * item.quantity,
                image_asset_id=item.image_asset_id,
            )
            for position, item in enumerate(items)
        ]
        totals = Totals.of(sum(line.line_total_cents for line in lines), address.zone)
        order = cls(
            id=order_id,
            number=number,
            public_token=public_token,
            status=OrderStatus.PENDING_PAYMENT,
            customer_account_id=customer_account_id,
            email=normalize_email(email),
            shipping_address=address,
            subtotal_cents=totals.subtotal_cents,
            shipping_cents=totals.shipping_cents,
            total_cents=totals.total_cents,
            tax_cents=totals.tax_cents,
            checkout_key=checkout_key,
            checkout_fingerprint=checkout_fingerprint,
            placed_at=now,
            updated_at=now,
            lines=lines,
        )
        return order, OrderPlaced(
            aggregate_id=order.id, occurred_at=now, number=number, total_cents=order.total_cents
        )

    @classmethod
    def import_paid(
        cls,
        *,
        order_id: UUID,
        number: str,
        public_token: str,
        channel: SalesChannel,
        external_ref: str,
        items: Sequence[PricedItem],
        email: str,
        address: PostalAddress,
        shipping_cents: int,
        paid_at: datetime,
        now: datetime,
    ) -> tuple["Order", list[DomainEvent]]:
        """An order a marketplace took and was paid for: it is binding as it arrives.

        Prices and shipping are the marketplace's; the shop's zones and rates do not apply.
        The order id is chosen by the marketplace module, which keeps its own record of the
        sale; ``external_ref`` makes importing the same sale twice impossible.
        """
        if channel is SalesChannel.SHOP:
            msg = "the shop's own orders are placed at checkout"
            raise ValueError(msg)
        if not items:
            msg = "an order needs at least one line"
            raise ValueError(msg)
        if shipping_cents < 0:
            raise InvalidFieldError("shipping_cents", "out_of_range", "must not be negative")
        lines = [
            OrderLine(
                id=new_id(),
                order_id=order_id,
                position=position,
                variant_id=item.variant_id,
                product_slug=item.product_slug,
                sku=item.sku,
                title=item.title,
                scale_code=item.scale_code,
                finish_code=item.finish_code,
                unit_price_cents=item.unit_price_cents,
                quantity=item.quantity,
                line_total_cents=item.unit_price_cents * item.quantity,
                image_asset_id=item.image_asset_id,
            )
            for position, item in enumerate(items)
        ]
        subtotal = sum(line.line_total_cents for line in lines)
        total = subtotal + shipping_cents
        # The checkout key and fingerprint stand for the sale itself: one order per sale.
        sale = f"{channel.value}:{external_ref}"
        order = cls(
            id=order_id,
            number=number,
            public_token=public_token,
            status=OrderStatus.PAID,
            customer_account_id=None,
            email=normalize_email(email),
            shipping_address=address,
            subtotal_cents=subtotal,
            shipping_cents=shipping_cents,
            total_cents=total,
            tax_cents=included_vat(total),
            checkout_key=uuid5(NAMESPACE_URL, f"modellbahn:{sale}"),
            checkout_fingerprint=hashlib.sha256(sale.encode()).hexdigest(),
            placed_at=paid_at,
            updated_at=now,
            paid_at=paid_at,
            channel=channel,
            external_ref=_text(external_ref, "external_ref", EXTERNAL_REF_MAX_LENGTH),
            lines=lines,
        )
        order.payments.append(
            Payment(
                id=new_id(),
                order_id=order.id,
                provider=channel.value,
                provider_ref=order.external_ref or "",
                status=PaymentStatus.CAPTURED,
                amount_cents=total,
                idempotency_key=uuid5(NAMESPACE_URL, f"modellbahn:payment:{sale}"),
                request_fingerprint=order.checkout_fingerprint,
                failure_code=None,
                created_at=now,
                updated_at=now,
            )
        )
        return order, [
            OrderPlaced(aggregate_id=order.id, occurred_at=now, number=number, total_cents=total),
            OrderPaid(aggregate_id=order.id, occurred_at=now, number=number, total_cents=total),
        ]

    @property
    def from_marketplace(self) -> bool:
        return self.channel is not SalesChannel.SHOP

    @property
    def is_guest_order(self) -> bool:
        return self.customer_account_id is None

    @property
    def item_count(self) -> int:
        return sum(line.quantity for line in self.lines)

    @property
    def captured_payment(self) -> Payment | None:
        return next((p for p in self.payments if p.status is PaymentStatus.CAPTURED), None)

    def payment_with_key(self, idempotency_key: UUID) -> Payment | None:
        return next((p for p in self.payments if p.idempotency_key == idempotency_key), None)

    @property
    def payment_due_at(self) -> datetime | None:
        """Until when an order waiting for its payment can be paid."""
        if self.status is not OrderStatus.PENDING_PAYMENT:
            return None
        return self.placed_at + PAYMENT_TIMEOUT

    def is_overdue(self, now: datetime) -> bool:
        """An order whose payment has not come in within 24 hours is given up."""
        return (
            self.status is OrderStatus.PENDING_PAYMENT and now - self.placed_at >= PAYMENT_TIMEOUT
        )

    def record_payment(
        self,
        result: ChargeResult,
        *,
        idempotency_key: UUID,
        request_fingerprint: str,
        now: datetime,
    ) -> list[DomainEvent]:
        """Note the provider's answer; a captured payment makes the order binding."""
        if self.status is not OrderStatus.PENDING_PAYMENT:
            raise OrderNotPayableError
        self.payments.append(
            Payment(
                id=new_id(),
                order_id=self.id,
                provider=result.provider,
                provider_ref=result.provider_ref,
                status=PaymentStatus.CAPTURED if result.captured else PaymentStatus.FAILED,
                amount_cents=self.total_cents,
                idempotency_key=idempotency_key,
                request_fingerprint=request_fingerprint,
                failure_code=result.failure_code,
                created_at=now,
                updated_at=now,
            )
        )
        self.updated_at = now
        if not result.captured:
            return []
        self.status = OrderStatus.PAID
        self.paid_at = now
        return [
            OrderPaid(
                aggregate_id=self.id,
                occurred_at=now,
                number=self.number,
                total_cents=self.total_cents,
            )
        ]

    def ship(self, *, carrier: str, tracking_number: str, now: datetime) -> OrderShipped:
        if self.status is not OrderStatus.PAID:
            msg = f"an order that is {self.status} cannot be shipped"
            raise InvalidOrderStateError(msg)
        self.carrier = _text(carrier, "carrier", CARRIER_MAX_LENGTH, required=False)
        self.tracking_number = _text(
            tracking_number, "tracking_number", TRACKING_NUMBER_MAX_LENGTH, required=False
        )
        self.status = OrderStatus.SHIPPED
        self.shipped_at = now
        self.updated_at = now
        return OrderShipped(
            aggregate_id=self.id, occurred_at=now, number=self.number, total_cents=self.total_cents
        )

    def cancel(self, *, reason: CancelReason, note: str, now: datetime) -> OrderCancelled:
        """Cancel an order that has not left the workshop; a captured payment is refunded.

        The caller refunds the payment with the provider first; this records it.
        """
        if self.status not in {OrderStatus.PENDING_PAYMENT, OrderStatus.PAID}:
            msg = f"an order that is {self.status} cannot be cancelled"
            raise InvalidOrderStateError(msg)
        payment = self.captured_payment
        if payment is not None:
            payment.refund(now)
        self.cancel_note = _text(note, "note", CANCEL_NOTE_MAX_LENGTH, required=False)
        self.status = OrderStatus.CANCELLED
        self.cancel_reason = reason
        self.cancelled_at = now
        self.updated_at = now
        return OrderCancelled(
            aggregate_id=self.id,
            occurred_at=now,
            number=self.number,
            total_cents=self.total_cents,
            refunded=payment is not None,
        )

    def adopt(self, account_id: UUID, now: datetime) -> bool:
        """Assign a guest order to the customer account with its (verified) address."""
        if self.customer_account_id is not None:
            return False
        self.customer_account_id = account_id
        self.updated_at = now
        return True
