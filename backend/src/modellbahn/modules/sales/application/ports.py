"""What the sales use cases need from the outside world, as protocols.

The infrastructure layer implements them; tests may substitute their own.
"""

from collections.abc import Collection
from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from types import TracebackType
from typing import Protocol, Self
from uuid import UUID

from modellbahn.modules.catalog.contracts.variants import SaleVariant
from modellbahn.modules.inventory.contracts.availability import PickProgress
from modellbahn.modules.marketplace.contracts.orders import ReceivedOrder
from modellbahn.modules.media.contracts.images import ImageView
from modellbahn.modules.sales.domain.invoices import Invoice, InvoiceDocument, InvoiceKind
from modellbahn.modules.sales.domain.labels import LabelAddress, ShippingLabel, ShippingProduct
from modellbahn.modules.sales.domain.model import (
    Cart,
    CustomerAddress,
    Order,
    OrderStatus,
    PaymentOutcome,
    PaymentStart,
)
from modellbahn.modules.sales.domain.withdrawals import Withdrawal
from modellbahn.modules.site.contracts.next_fair import NextFair
from modellbahn.platform.events import DomainEvent


@dataclass(frozen=True, slots=True)
class OrderCursor:
    """Keyset position: time and id of the last order of the previous page (newest first)."""

    placed_at: datetime
    id: UUID


@dataclass(frozen=True, slots=True)
class OrderQuery:
    limit: int
    customer_account_id: UUID | None = None
    statuses: frozenset[OrderStatus] | None = None
    text: str | None = None
    """Part of the order number or of the e-mail address (staff search)."""
    after: OrderCursor | None = None


class CartRepository(Protocol):
    async def get(self, cart_id: UUID, *, for_update: bool = False) -> Cart | None: ...

    def add(self, cart: Cart) -> None: ...

    async def delete_expired(self, now: datetime) -> int:
        """Remove carts that expired before ``now``; the number removed."""
        ...


class OrderRepository(Protocol):
    async def get(self, order_id: UUID, *, for_update: bool = False) -> Order | None: ...

    async def get_by_token(self, public_token: str, *, for_update: bool = False) -> Order | None:
        """The order behind a status link (guests have nothing else)."""
        ...

    async def get_by_number(self, number: str) -> Order | None: ...

    async def get_by_checkout_key(self, checkout_key: UUID) -> Order | None: ...

    async def next_serial(self) -> int:
        """The next serial of the order numbers (a sequence: gaps are possible)."""
        ...

    def add(self, order: Order) -> None: ...

    async def search(self, query: OrderQuery) -> list[Order]:
        """Orders matching ``query``, newest first, one page."""
        ...

    async def guest_orders_for(self, email: str) -> list[Order]:
        """Guest orders placed with ``email`` (any letter case), locked for adoption."""
        ...

    async def overdue_ids(self, now: datetime, limit: int) -> list[UUID]:
        """Orders still waiting for their payment after their deadline, the oldest first.

        24 hours after the order; ten days if the customer chose a bank transfer.
        """
        ...

    async def id_by_payment(self, provider: str, provider_ref: str) -> UUID | None:
        """The order of the provider's payment, if it is one of ours."""
        ...

    async def pending_payment_ids(
        self, provider: str, started_before: datetime, limit: int
    ) -> list[UUID]:
        """Orders with a payment on this provider's page begun before the cut-off, oldest first."""
        ...

    async def repayment_ids(self, limit: int) -> list[UUID]:
        """Orders whose refunded bank transfer still has to go back, oldest refund first."""
        ...


class WithdrawalRepository(Protocol):
    def add(self, withdrawal: Withdrawal) -> None: ...

    async def get(self, withdrawal_id: UUID) -> Withdrawal | None: ...

    async def recent(self, *, limit: int, order_id: UUID | None = None) -> list[Withdrawal]:
        """The latest declarations first; only those naming the order, if one is given."""
        ...

    async def received_since(self, since: datetime) -> list[Withdrawal]:
        """The declarations that came in since then, oldest first."""
        ...


class AddressRepository(Protocol):
    async def book(self, account_id: UUID, *, for_update: bool = False) -> list[CustomerAddress]:
        """The account's addresses, oldest first."""
        ...

    def add(self, address: CustomerAddress) -> None: ...

    async def delete(self, address: CustomerAddress) -> None: ...

    async def delete_book(self, account_id: UUID) -> int:
        """Remove every address of the account; the number removed."""
        ...


class Catalog(Protocol):
    """The catalogue's variants as the shop sells them right now."""

    async def sale_variants(self, variant_ids: Collection[UUID]) -> dict[UUID, SaleVariant]: ...

    async def shop_lead_time(self) -> tuple[int, int]:
        """The shop's lead time in weeks, from and to, for variants without their own."""
        ...


class Images(Protocol):
    """The images of the media module, for cart and order lines."""

    async def load(self, asset_ids: Collection[UUID]) -> dict[UUID, ImageView]: ...


class Accounts(Protocol):
    """What sales may ask the identity module."""

    async def verified_customer(self, email: str) -> UUID | None:
        """The customer account whose verified address is ``email``, if any."""
        ...

    async def verified_email(self, account_id: UUID) -> str | None:
        """The verified address of an active customer account, if it has one."""
        ...


class Inventory(Protocol):
    """What sales may ask the inventory module."""

    async def free_units(self, variant_ids: Collection[UUID]) -> dict[UUID, int]:
        """Units on the shelves that nobody has been promised (missing means none)."""
        ...

    async def pick_progress(self, order_id: UUID) -> PickProgress:
        """How many of the order's pieces are picked for packing."""
        ...

    async def orders_served_by_plate(self, job_id: UUID) -> set[UUID]:
        """Orders with a piece waiting whose bill of materials has a part on this plate."""
        ...


@dataclass(frozen=True, slots=True)
class DigestFacts:
    """What the morning mail says: the day's work and yesterday's sales."""

    to_pack: int
    """Paid orders with every piece there: the parcels to pack."""
    oldest_to_pack: str | None
    making_pieces: int
    """Paid pieces the workshop still makes, and for how many orders."""
    making_orders: int
    unpaid_overdue: int
    """Orders waiting three days or more for the money."""
    paid_yesterday: int
    paid_yesterday_cents: int
    plates_queued: int
    plates_printing: int
    plates_post_processing: int
    printers_down: list[str]


class Digests(Protocol):
    """The morning mail's figures (ADR 0034), and the claim that it goes out once a day."""

    async def claim(self, day: date, now: datetime) -> bool:
        """True for the first caller of the day; false if the mail went out already."""
        ...

    async def facts(self, now: datetime) -> DigestFacts: ...


# --- Sales report (ADR 0039) -------------------------------------------------------


class ReportChannel(StrEnum):
    """Where a sale happened: the online channels of orders, and those of pieces booked out."""

    SHOP = "shop"
    EBAY = "ebay"
    FAIR = "fair"
    STORE = "store"
    PRIVATE = "private"
    OTHER = "other"
    UNKNOWN = "unknown"
    """Booked out as sold without saying where."""


class SoldKind(StrEnum):
    ORDER_LINE = "order_line"
    PIECE = "piece"
    """A piece booked out as sold: its channel and price can be entered afterwards."""


@dataclass(frozen=True, slots=True)
class SoldLine:
    kind: SoldKind
    key: str
    """The order line's id, or the piece's code: stable for lists and links."""
    channel: ReportChannel
    sold_at: datetime
    title: str
    sku: str
    quantity: int
    unit_price_cents: int
    price_from_shop: bool
    """The piece's price was not entered; today's shop price stands in."""
    order_id: UUID | None = None
    order_number: str | None = None
    unit_code: str | None = None
    note: str = ""
    staff_name: str | None = None
    variant_id: UUID | None = None
    """What was sold, for the evaluation by model and scale; empty if the catalogue lost it."""
    product_name: str = ""
    """``IFA ADK 70 Autokran``: the model, the same for all its scales and finishes."""
    product_slug: str = ""
    scale_code: str = ""
    """``H0``, ``TT``: what the evaluation groups by besides the model."""
    variant_name: str = ""
    """``H0 · Fertigmodell, Gelb``: the variant without the model's name."""

    @property
    def total_cents(self) -> int:
        return self.unit_price_cents * self.quantity


class SalesLedger(Protocol):
    """Reads what was sold across the modules, inside the caller's transaction."""

    async def sold(self, since: datetime, until: datetime) -> list[SoldLine]: ...


class Fairs(Protocol):
    """What sales may ask the site module: the next fair, for a line in the mails."""

    async def next_fair(self, today: date) -> NextFair | None: ...


class Marketplace(Protocol):
    """What sales may ask the marketplace module: a sale made there, to take over."""

    async def received_order(self, marketplace_order_id: UUID) -> ReceivedOrder | None: ...


@dataclass(frozen=True, slots=True)
class PaymentRequest:
    """What the provider needs to begin a payment for an order."""

    payment_id: UUID
    """Our id of the payment attempt; the provider keeps it as its reference."""
    order_number: str
    amount_cents: int
    method: str
    """The test payment's chosen outcome; SumUp ignores it (the customer chooses there)."""
    return_url: str
    """Where the customer comes back to after paying on the provider's page."""
    valid_until: datetime
    """After this the provider's page no longer takes the payment (the order is given up)."""


class PaymentGateway(Protocol):
    """The payment provider behind an anti-corruption layer (KONZEPT §2.6, ADR 0019).

    Every method raises :class:`~modellbahn.modules.sales.domain.errors.PaymentUnavailableError`
    if the provider cannot be reached; nothing has been charged or refunded then.
    """

    @property
    def provider(self) -> str:
        """The name stored with each payment (``mock``, ``sumup``)."""
        ...

    @property
    def takes_payments(self) -> bool:
        """False if no provider is connected: the shop then takes no orders."""
        ...

    async def begin(self, request: PaymentRequest) -> PaymentStart:
        """Begin a payment, answered at once (declined too) or later on the provider page."""
        ...

    async def outcome(self, provider_ref: str) -> PaymentOutcome:
        """The provider's current answer about a payment that went to its page."""
        ...

    async def abandon(self, provider_ref: str) -> None:
        """Close the provider's page so that nothing can be paid there any more.

        Also raises ``PaymentUnavailableError`` if the page was used meanwhile (paid or
        failed): only :meth:`outcome` tells then what happened.
        """
        ...

    async def refund(self, *, refund_ref: str, amount_cents: int) -> None:
        """Give back ``amount_cents`` of the payment: all of it, or a part after a return."""
        ...

    async def aclose(self) -> None:
        """Release the provider's connections (at shutdown)."""
        ...


@dataclass(frozen=True, slots=True)
class LabelRequest:
    """What the carrier needs to book a label (ADR 0023)."""

    reference: str
    """The order number: printed on the label and kept by the carrier."""
    product: ShippingProduct
    shipper: LabelAddress
    consignee: LabelAddress
    weight_g: int


@dataclass(frozen=True, slots=True)
class BookedLabel:
    shipment_number: str
    document: bytes
    """The label as a PDF, in the configured print format."""
    print_format: str


class Carrier(Protocol):
    """The parcel carrier behind an anti-corruption layer (ADR 0023).

    Raises :class:`~modellbahn.modules.sales.domain.errors.CarrierUnavailableError` if it
    cannot be reached (nothing was booked) and ``CarrierRejectedError`` with its reason if
    it refuses.
    """

    @property
    def name(self) -> str:
        """As it appears in the dispatch and the customer's e-mail, e.g. ``DHL``."""
        ...

    @property
    def books_labels(self) -> bool:
        """False if no carrier is connected: the staff type the shipment number in."""
        ...

    async def book(self, request: LabelRequest) -> BookedLabel: ...

    async def cancel(self, shipment_number: str) -> None:
        """Drop a label that was not used; done already counts as done."""
        ...

    async def aclose(self) -> None: ...


class LabelRepository(Protocol):
    async def active_for(self, order_id: UUID, *, for_update: bool = False) -> ShippingLabel | None:
        """The order's label in force, if any."""
        ...

    def add(self, label: ShippingLabel) -> None: ...


class InvoiceRepository(Protocol):
    async def for_order(self, order_id: UUID) -> list[Invoice]:
        """The order's invoice and corrections, oldest first."""
        ...

    async def by_source(self, order_id: UUID, source: str) -> Invoice | None:
        """What was issued for this occasion already (issuing is idempotent)."""
        ...

    async def get(self, invoice_id: UUID) -> Invoice | None: ...

    async def next_serial(self, kind: InvoiceKind, year: int) -> int:
        """The next number of the series, without gaps: the counter stays locked until the
        transaction ends, so a rolled back issue gives its number to the next one."""
        ...

    def add(self, invoice: Invoice) -> None: ...


class InvoiceRenderer(Protocol):
    """Draws an invoice or correction as a PDF."""

    def render(self, document: InvoiceDocument) -> bytes: ...


class SalesUnitOfWork(Protocol):
    """One transaction over the sales repositories (see ``platform.uow``)."""

    @property
    def carts(self) -> CartRepository: ...

    @property
    def orders(self) -> OrderRepository: ...

    @property
    def addresses(self) -> AddressRepository: ...

    @property
    def withdrawals(self) -> WithdrawalRepository: ...

    @property
    def labels(self) -> LabelRepository: ...

    @property
    def invoices(self) -> InvoiceRepository: ...

    @property
    def catalog(self) -> Catalog: ...

    @property
    def images(self) -> Images: ...

    @property
    def accounts(self) -> Accounts: ...

    @property
    def inventory(self) -> Inventory: ...

    @property
    def fairs(self) -> Fairs: ...

    @property
    def digests(self) -> Digests: ...

    @property
    def sales_ledger(self) -> SalesLedger: ...

    @property
    def marketplace(self) -> Marketplace: ...

    async def __aenter__(self) -> Self: ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...

    def publish(self, *events: DomainEvent) -> None: ...

    async def flush(self) -> None: ...

    async def commit(self) -> None: ...
