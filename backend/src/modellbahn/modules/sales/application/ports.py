"""What the sales use cases need from the outside world, as protocols.

The infrastructure layer implements them; tests may substitute their own.
"""

from collections.abc import Collection
from dataclasses import dataclass
from datetime import date, datetime
from types import TracebackType
from typing import Protocol, Self
from uuid import UUID

from modellbahn.modules.catalog.contracts.variants import SaleVariant
from modellbahn.modules.inventory.contracts.availability import PickProgress
from modellbahn.modules.media.contracts.images import ImageView
from modellbahn.modules.sales.domain.model import (
    Cart,
    ChargeResult,
    CustomerAddress,
    Order,
    OrderStatus,
)
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

    async def overdue_ids(self, placed_before: datetime, limit: int) -> list[UUID]:
        """Orders still waiting for their payment that were placed before the cut-off."""
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


class Fairs(Protocol):
    """What sales may ask the site module: the next fair, for a line in the mails."""

    async def next_fair(self, today: date) -> NextFair | None: ...


class PaymentGateway(Protocol):
    """The payment provider behind an anti-corruption layer (KONZEPT §2.6).

    Both methods raise :class:`~modellbahn.modules.sales.domain.errors.PaymentUnavailableError`
    if the provider cannot be reached; nothing has been charged or refunded then.
    """

    async def charge(self, *, order_number: str, amount_cents: int, method: str) -> ChargeResult:
        """Charge the amount; a declined payment is a result, not an error."""
        ...

    async def refund(self, *, provider_ref: str, amount_cents: int) -> None: ...


class SalesUnitOfWork(Protocol):
    """One transaction over the sales repositories (see ``platform.uow``)."""

    @property
    def carts(self) -> CartRepository: ...

    @property
    def orders(self) -> OrderRepository: ...

    @property
    def addresses(self) -> AddressRepository: ...

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
