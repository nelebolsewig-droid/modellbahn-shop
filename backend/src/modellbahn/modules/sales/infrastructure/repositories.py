"""SQLAlchemy implementations of the sales repositories and unit of work.

Repositories only read and stage changes; committing is the unit of work's job.
"""

from collections.abc import Collection
from datetime import date, datetime
from functools import partial
from uuid import UUID

from sqlalchemy import Select, delete, or_, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from modellbahn.modules.catalog.contracts.variants import SaleVariant, load_sale_variants
from modellbahn.modules.identity.contracts.accounts import (
    find_verified_customer,
    get_account_summary,
)
from modellbahn.modules.inventory.contracts.availability import PickProgress
from modellbahn.modules.inventory.contracts.stock import load_free_units, load_pick_progress
from modellbahn.modules.marketplace.contracts.orders import ReceivedOrder, load_received_order
from modellbahn.modules.media.contracts.images import ImageView, load_images
from modellbahn.modules.sales.application.ports import OrderQuery
from modellbahn.modules.sales.domain.model import (
    Cart,
    CustomerAddress,
    Order,
    OrderStatus,
    SalesChannel,
)
from modellbahn.modules.sales.infrastructure.mapping import start_mappers
from modellbahn.modules.sales.infrastructure.tables import (
    carts,
    customer_addresses,
    order_number_seq,
    orders,
)
from modellbahn.modules.site.contracts.fairs import load_next_fair
from modellbahn.modules.site.contracts.next_fair import NextFair
from modellbahn.platform.uow import UnitOfWork


def _locked[*Ts](statement: Select[*Ts], for_update: bool) -> Select[*Ts]:
    if not for_update:
        return statement
    # FOR NO KEY UPDATE: no use case changes a primary key, and inserting a payment or
    # an address only takes a key-share lock on the row it refers to.
    return statement.with_for_update(key_share=True).execution_options(populate_existing=True)


def _like(text: str) -> str:
    escaped = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


class SqlCartRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, cart_id: UUID, *, for_update: bool = False) -> Cart | None:
        statement = _locked(select(Cart).where(carts.c.id == cart_id), for_update)
        return (await self._session.execute(statement)).scalar_one_or_none()

    def add(self, cart: Cart) -> None:
        self._session.add(cart)

    async def delete_expired(self, now: datetime) -> int:
        result = await self._session.execute(delete(carts).where(carts.c.expires_at <= now))
        return int(result.rowcount)  # type: ignore[attr-defined]


class SqlOrderRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, order_id: UUID, *, for_update: bool = False) -> Order | None:
        statement = _locked(select(Order).where(orders.c.id == order_id), for_update)
        return (await self._session.execute(statement)).scalar_one_or_none()

    async def get_by_token(self, public_token: str, *, for_update: bool = False) -> Order | None:
        statement = _locked(select(Order).where(orders.c.public_token == public_token), for_update)
        return (await self._session.execute(statement)).scalar_one_or_none()

    async def get_by_number(self, number: str) -> Order | None:
        statement = select(Order).where(orders.c.number == number)
        return (await self._session.execute(statement)).scalar_one_or_none()

    async def get_by_checkout_key(self, checkout_key: UUID) -> Order | None:
        statement = select(Order).where(orders.c.checkout_key == checkout_key)
        return (await self._session.execute(statement)).scalar_one_or_none()

    async def next_serial(self) -> int:
        return int(await self._session.scalar(select(order_number_seq.next_value())) or 0)

    def add(self, order: Order) -> None:
        self._session.add(order)

    async def search(self, query: OrderQuery) -> list[Order]:
        statement = select(Order).order_by(orders.c.placed_at.desc(), orders.c.id.desc())
        if query.customer_account_id is not None:
            statement = statement.where(orders.c.customer_account_id == query.customer_account_id)
        if query.statuses is not None:
            statement = statement.where(orders.c.status.in_(sorted(query.statuses)))
        if query.text:
            pattern = _like(query.text)
            statement = statement.where(
                or_(orders.c.number.ilike(pattern), orders.c.email.ilike(pattern))
            )
        if query.after is not None:
            statement = statement.where(
                tuple_(orders.c.placed_at, orders.c.id)
                < tuple_(query.after.placed_at, query.after.id)
            )
        return list((await self._session.execute(statement.limit(query.limit))).scalars())

    async def guest_orders_for(self, email: str) -> list[Order]:
        # email is citext: the comparison ignores letter case, as addresses do. A buyer on
        # a marketplace is the marketplace's customer, so those orders stay where they are.
        statement = _locked(
            select(Order).where(
                orders.c.customer_account_id.is_(None),
                orders.c.channel == SalesChannel.SHOP,
                orders.c.email == email,
            ),
            for_update=True,
        )
        return list((await self._session.execute(statement)).scalars())

    async def overdue_ids(self, placed_before: datetime, limit: int) -> list[UUID]:
        statement = (
            select(orders.c.id)
            .where(
                orders.c.status == OrderStatus.PENDING_PAYMENT,
                orders.c.placed_at <= placed_before,
            )
            .order_by(orders.c.placed_at)
            .limit(limit)
        )
        return list((await self._session.execute(statement)).scalars())


class SqlAddressRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def book(self, account_id: UUID, *, for_update: bool = False) -> list[CustomerAddress]:
        statement = _locked(
            select(CustomerAddress)
            .where(customer_addresses.c.account_id == account_id)
            .order_by(customer_addresses.c.created_at, customer_addresses.c.id),
            for_update,
        )
        return list((await self._session.execute(statement)).scalars())

    def add(self, address: CustomerAddress) -> None:
        self._session.add(address)

    async def delete(self, address: CustomerAddress) -> None:
        await self._session.delete(address)

    async def delete_book(self, account_id: UUID) -> int:
        result = await self._session.execute(
            delete(customer_addresses).where(customer_addresses.c.account_id == account_id)
        )
        return int(result.rowcount)  # type: ignore[attr-defined]


class SqlCatalog:
    """The catalogue's variant facade, inside this unit of work's transaction."""

    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    async def sale_variants(self, variant_ids: Collection[UUID]) -> dict[UUID, SaleVariant]:
        return await load_sale_variants(self._uow, variant_ids)


class SqlImages:
    """The media module's image facade, inside this unit of work's transaction."""

    def __init__(self, uow: UnitOfWork, public_base_url: str) -> None:
        self._uow = uow
        self._public_base_url = public_base_url

    async def load(self, asset_ids: Collection[UUID]) -> dict[UUID, ImageView]:
        return await load_images(self._uow, asset_ids, public_base_url=self._public_base_url)


class SqlAccounts:
    """The identity module's account facade, inside this unit of work's transaction."""

    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    async def verified_customer(self, email: str) -> UUID | None:
        return await find_verified_customer(self._uow, email)

    async def verified_email(self, account_id: UUID) -> str | None:
        account = await get_account_summary(self._uow, account_id)
        if account is None or not account.active or not account.email_verified:
            return None
        return account.email


class SqlInventory:
    """The inventory module's stock facade, inside this unit of work's transaction."""

    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    async def free_units(self, variant_ids: Collection[UUID]) -> dict[UUID, int]:
        return await load_free_units(self._uow, variant_ids)

    async def pick_progress(self, order_id: UUID) -> PickProgress:
        return await load_pick_progress(self._uow, order_id)


class SqlFairs:
    """The site module's fair facade, inside this unit of work's transaction."""

    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    async def next_fair(self, today: date) -> NextFair | None:
        return await load_next_fair(self._uow, today)


class SqlMarketplace:
    """The marketplace module's order facade, inside this unit of work's transaction."""

    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    async def received_order(self, marketplace_order_id: UUID) -> ReceivedOrder | None:
        return await load_received_order(self._uow, marketplace_order_id)


class SqlSalesUnitOfWork(UnitOfWork):
    """Unit of work with the sales repositories attached."""

    carts: SqlCartRepository
    orders: SqlOrderRepository
    addresses: SqlAddressRepository
    catalog: SqlCatalog
    images: SqlImages
    accounts: SqlAccounts
    inventory: SqlInventory
    fairs: SqlFairs
    marketplace: SqlMarketplace

    def __init__(
        self, session_factory: async_sessionmaker[AsyncSession], *, public_base_url: str
    ) -> None:
        super().__init__(session_factory)
        self._public_base_url = public_base_url

    def _attach(self, session: AsyncSession) -> None:
        start_mappers()
        self.carts = SqlCartRepository(session)
        self.orders = SqlOrderRepository(session)
        self.addresses = SqlAddressRepository(session)
        self.catalog = SqlCatalog(self)
        self.images = SqlImages(self, self._public_base_url)
        self.accounts = SqlAccounts(self)
        self.inventory = SqlInventory(self)
        self.fairs = SqlFairs(self)
        self.marketplace = SqlMarketplace(self)


def sales_uow_factory(
    session_factory: async_sessionmaker[AsyncSession], *, public_base_url: str
) -> partial[SqlSalesUnitOfWork]:
    """The factory the sales services get: a fresh unit of work per call."""
    return partial(SqlSalesUnitOfWork, session_factory, public_base_url=public_base_url)
