"""SQLAlchemy implementations of the sales repositories and unit of work.

Repositories only read and stage changes; committing is the unit of work's job.
"""

from collections.abc import Collection
from datetime import date, datetime, timedelta
from functools import partial
from typing import Final
from uuid import UUID

from sqlalchemy import Select, and_, delete, exists, func, or_, select, tuple_
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from modellbahn.modules.catalog.contracts.variants import (
    SaleVariant,
    load_sale_variants,
    load_shop_lead_time,
)
from modellbahn.modules.identity.contracts.accounts import (
    find_verified_customer,
    get_account_summary,
    load_display_names,
)
from modellbahn.modules.inventory.contracts.availability import PickProgress
from modellbahn.modules.inventory.contracts.demand import load_waiting_pieces
from modellbahn.modules.inventory.contracts.sales import SaleChannel, load_off_site_sales
from modellbahn.modules.inventory.contracts.stock import load_free_units, load_pick_progress
from modellbahn.modules.manufacturing.contracts.parts import (
    load_bill_of_materials,
    load_print_job_parts,
    load_workshop_state,
)
from modellbahn.modules.marketplace.contracts.orders import ReceivedOrder, load_received_order
from modellbahn.modules.media.contracts.images import ImageView, load_images
from modellbahn.modules.sales.application.mails import SHOP_TIME_ZONE
from modellbahn.modules.sales.application.ports import (
    DigestFacts,
    OrderQuery,
    ReportChannel,
    SoldKind,
    SoldLine,
)
from modellbahn.modules.sales.domain.invoices import Invoice, InvoiceKind
from modellbahn.modules.sales.domain.labels import LabelStatus, ShippingLabel
from modellbahn.modules.sales.domain.model import (
    BANK_TRANSFER,
    BANK_TRANSFER_TIMEOUT,
    PAYMENT_TIMEOUT,
    Cart,
    CustomerAddress,
    Order,
    OrderStatus,
    PaymentStatus,
    SalesChannel,
)
from modellbahn.modules.sales.domain.withdrawals import Withdrawal
from modellbahn.modules.sales.infrastructure.mapping import start_mappers
from modellbahn.modules.sales.infrastructure.tables import (
    carts,
    customer_addresses,
    daily_digests,
    invoice_counters,
    invoices,
    order_lines,
    order_number_seq,
    orders,
    payments,
    shipping_labels,
    withdrawals,
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
            # Also eBay's order number, which a buyer quotes.
            statement = statement.where(
                or_(
                    orders.c.number.ilike(pattern),
                    orders.c.email.ilike(pattern),
                    orders.c.external_ref.ilike(pattern),
                )
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

    async def overdue_ids(self, now: datetime, limit: int) -> list[UUID]:
        # Orders waiting for a transfer stay out of the 24-hour batch, or they would fill it.
        by_transfer = exists().where(
            payments.c.order_id == orders.c.id, payments.c.provider == BANK_TRANSFER
        )
        statement = (
            select(orders.c.id)
            .where(
                orders.c.status == OrderStatus.PENDING_PAYMENT,
                or_(
                    and_(orders.c.placed_at <= now - PAYMENT_TIMEOUT, ~by_transfer),
                    orders.c.placed_at <= now - BANK_TRANSFER_TIMEOUT,
                ),
            )
            .order_by(orders.c.placed_at)
            .limit(limit)
        )
        return list((await self._session.execute(statement)).scalars())

    async def id_by_payment(self, provider: str, provider_ref: str) -> UUID | None:
        statement = select(payments.c.order_id).where(
            payments.c.provider == provider, payments.c.provider_ref == provider_ref
        )
        return (await self._session.execute(statement)).scalar_one_or_none()

    async def pending_payment_ids(
        self, provider: str, started_before: datetime, limit: int
    ) -> list[UUID]:
        # Only the configured provider's: another one's could never be asked, and would hold
        # the batch for good.
        statement = (
            select(payments.c.order_id)
            .where(
                payments.c.status == PaymentStatus.PENDING,
                payments.c.provider == provider,
                payments.c.created_at <= started_before,
            )
            .order_by(payments.c.created_at)
            .limit(limit)
        )
        return list((await self._session.execute(statement)).scalars())


class SqlWithdrawalRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def add(self, withdrawal: Withdrawal) -> None:
        self._session.add(withdrawal)

    async def get(self, withdrawal_id: UUID) -> Withdrawal | None:
        return await self._session.get(Withdrawal, withdrawal_id)

    async def recent(self, *, limit: int, order_id: UUID | None = None) -> list[Withdrawal]:
        statement = select(Withdrawal).order_by(
            withdrawals.c.received_at.desc(), withdrawals.c.id.desc()
        )
        if order_id is not None:
            statement = statement.where(withdrawals.c.order_id == order_id)
        return list((await self._session.execute(statement.limit(limit))).scalars())

    async def received_since(self, since: datetime) -> list[Withdrawal]:
        statement = (
            select(Withdrawal)
            .where(withdrawals.c.received_at >= since)
            .order_by(withdrawals.c.received_at, withdrawals.c.id)
        )
        return list((await self._session.execute(statement)).scalars())


class SqlLabelRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def active_for(self, order_id: UUID, *, for_update: bool = False) -> ShippingLabel | None:
        statement = select(ShippingLabel).where(
            shipping_labels.c.order_id == order_id,
            shipping_labels.c.status == LabelStatus.ACTIVE,
        )
        if for_update:
            statement = statement.with_for_update().execution_options(populate_existing=True)
        return (await self._session.execute(statement)).scalars().one_or_none()

    def add(self, label: ShippingLabel) -> None:
        self._session.add(label)


class SqlInvoiceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def for_order(self, order_id: UUID) -> list[Invoice]:
        statement = (
            select(Invoice)
            .where(invoices.c.order_id == order_id)
            .order_by(invoices.c.issued_at, invoices.c.number)
        )
        return list((await self._session.execute(statement)).scalars())

    async def by_source(self, order_id: UUID, source: str) -> Invoice | None:
        statement = select(Invoice).where(
            invoices.c.order_id == order_id, invoices.c.source == source
        )
        return (await self._session.execute(statement)).scalars().one_or_none()

    async def get(self, invoice_id: UUID) -> Invoice | None:
        return await self._session.get(Invoice, invoice_id)

    async def next_serial(self, kind: InvoiceKind, year: int) -> int:
        # The upsert keeps the counter's row locked until the transaction ends: a second
        # issue waits, and a rolled back one leaves no gap.
        statement = (
            insert(invoice_counters)
            .values(kind=kind, year=year, last_serial=1)
            .on_conflict_do_update(
                index_elements=[invoice_counters.c.kind, invoice_counters.c.year],
                set_={"last_serial": invoice_counters.c.last_serial + 1},
            )
            .returning(invoice_counters.c.last_serial)
        )
        return int((await self._session.execute(statement)).scalar_one())

    def add(self, invoice: Invoice) -> None:
        self._session.add(invoice)


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

    async def shop_lead_time(self) -> tuple[int, int]:
        return await load_shop_lead_time(self._uow)


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

    async def orders_served_by_plate(self, job_id: UUID) -> set[UUID]:
        on_plate = await load_print_job_parts(self._uow, job_id)
        pieces = await load_waiting_pieces(self._uow)
        if not on_plate or not pieces:
            return set()
        variants = await load_sale_variants(self._uow, {piece.variant_id for piece in pieces})
        parts_of_scale: dict[UUID, set[UUID]] = {}
        served: set[UUID] = set()
        for piece in pieces:
            variant = variants.get(piece.variant_id)
            if variant is None:
                continue
            scale_id = variant.product_scale_id
            if scale_id not in parts_of_scale:
                kit = await load_bill_of_materials(self._uow, scale_id)
                parts_of_scale[scale_id] = {line.part.part_id for line in kit}
            if parts_of_scale[scale_id] & on_plate:
                served.add(piece.order_id)
        return served


UNPAID_FOR: Final = timedelta(days=3)
"""How long an order waits for its money before the morning mail names it."""


class SqlDigests:
    """The morning mail's figures, read across the modules inside this transaction."""

    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    async def claim(self, day: date, now: datetime) -> bool:
        claimed = await self._uow.session.execute(
            insert(daily_digests)
            .values(day=day, sent_at=now)
            .on_conflict_do_nothing(index_elements=[daily_digests.c.day])
            .returning(daily_digests.c.day)
        )
        return claimed.first() is not None

    async def facts(self, now: datetime) -> DigestFacts:
        session = self._uow.session
        waiting = await load_waiting_pieces(self._uow)
        making_orders = {piece.order_id for piece in waiting}
        paid = (
            await session.execute(
                select(orders.c.id, orders.c.number)
                .where(orders.c.status == OrderStatus.PAID)
                .order_by(orders.c.paid_at, orders.c.number)
            )
        ).all()
        ready = [row.number for row in paid if row.id not in making_orders]
        overdue = await session.scalar(
            select(func.count()).where(
                orders.c.status == OrderStatus.PENDING_PAYMENT,
                orders.c.placed_at <= now - UNPAID_FOR,
            )
        )
        local_today = now.astimezone(SHOP_TIME_ZONE).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        yesterday = (
            await session.execute(
                select(func.count(), func.coalesce(func.sum(orders.c.total_cents), 0)).where(
                    orders.c.paid_at >= local_today - timedelta(days=1),
                    orders.c.paid_at < local_today,
                    orders.c.status != OrderStatus.CANCELLED,
                )
            )
        ).one()
        workshop = await load_workshop_state(self._uow)
        return DigestFacts(
            to_pack=len(ready),
            oldest_to_pack=ready[0] if ready else None,
            making_pieces=len(waiting),
            making_orders=len(making_orders),
            unpaid_overdue=int(overdue or 0),
            paid_yesterday=int(yesterday[0]),
            paid_yesterday_cents=int(yesterday[1]),
            plates_queued=workshop.queued,
            plates_printing=workshop.printing,
            plates_post_processing=workshop.post_processing,
            printers_down=workshop.down,
        )


class SqlFairs:
    """The site module's fair facade, inside this unit of work's transaction."""

    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    async def next_fair(self, today: date) -> NextFair | None:
        return await load_next_fair(self._uow, today)


_OFF_SITE_CHANNELS: Final = {
    SaleChannel.FAIR: ReportChannel.FAIR,
    SaleChannel.STORE: ReportChannel.STORE,
    SaleChannel.PRIVATE: ReportChannel.PRIVATE,
    SaleChannel.OTHER: ReportChannel.OTHER,
}
_ORDER_CHANNELS: Final = {
    SalesChannel.SHOP: ReportChannel.SHOP,
    SalesChannel.EBAY: ReportChannel.EBAY,
}


class SqlSalesLedger:
    """What was sold (ADR 0039): paid order lines here, pieces booked out as sold from
    the inventory module, named by the catalogue."""

    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    async def sold(self, since: datetime, until: datetime) -> list[SoldLine]:
        return [*await self._order_lines(since, until), *await self._pieces(since, until)]

    async def _order_lines(self, since: datetime, until: datetime) -> list[SoldLine]:
        rows = await self._uow.session.execute(
            select(
                order_lines.c.id,
                order_lines.c.title,
                order_lines.c.sku,
                order_lines.c.quantity,
                order_lines.c.unit_price_cents,
                orders.c.id.label("order_id"),
                orders.c.number,
                orders.c.channel,
                orders.c.paid_at,
            )
            .join(orders, orders.c.id == order_lines.c.order_id)
            .where(
                orders.c.paid_at >= since,
                orders.c.paid_at < until,
                orders.c.status != OrderStatus.CANCELLED,
            )
        )
        return [
            SoldLine(
                kind=SoldKind.ORDER_LINE,
                key=str(row.id),
                channel=_ORDER_CHANNELS[row.channel],
                sold_at=row.paid_at,
                title=row.title,
                sku=row.sku,
                quantity=row.quantity,
                unit_price_cents=row.unit_price_cents,
                price_from_shop=False,
                order_id=row.order_id,
                order_number=row.number,
            )
            for row in rows
        ]

    async def _pieces(self, since: datetime, until: datetime) -> list[SoldLine]:
        pieces = await load_off_site_sales(self._uow, since, until)
        variants = await load_sale_variants(self._uow, {piece.variant_id for piece in pieces})
        names = await load_display_names(
            self._uow, {piece.staff_id for piece in pieces if piece.staff_id}
        )
        lines: list[SoldLine] = []
        for piece in pieces:
            variant = variants.get(piece.variant_id)
            shop_price = variant.price_cents if variant else 0
            lines.append(
                SoldLine(
                    kind=SoldKind.PIECE,
                    key=piece.unit_code,
                    channel=_OFF_SITE_CHANNELS[piece.channel]
                    if piece.channel
                    else ReportChannel.UNKNOWN,
                    sold_at=piece.sold_at,
                    title=variant.title if variant else "Unbekannter Artikel",
                    sku=variant.sku if variant else "",
                    quantity=1,
                    unit_price_cents=shop_price if piece.price_cents is None else piece.price_cents,
                    price_from_shop=piece.price_cents is None,
                    unit_code=piece.unit_code,
                    note=piece.note,
                    staff_name=names.get(piece.staff_id) if piece.staff_id else None,
                )
            )
        return lines


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
    withdrawals: SqlWithdrawalRepository
    labels: SqlLabelRepository
    invoices: SqlInvoiceRepository
    catalog: SqlCatalog
    images: SqlImages
    accounts: SqlAccounts
    inventory: SqlInventory
    fairs: SqlFairs
    digests: SqlDigests
    sales_ledger: SqlSalesLedger
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
        self.withdrawals = SqlWithdrawalRepository(session)
        self.labels = SqlLabelRepository(session)
        self.invoices = SqlInvoiceRepository(session)
        self.catalog = SqlCatalog(self)
        self.images = SqlImages(self, self._public_base_url)
        self.accounts = SqlAccounts(self)
        self.inventory = SqlInventory(self)
        self.fairs = SqlFairs(self)
        self.digests = SqlDigests(self)
        self.sales_ledger = SqlSalesLedger(self)
        self.marketplace = SqlMarketplace(self)


def sales_uow_factory(
    session_factory: async_sessionmaker[AsyncSession], *, public_base_url: str
) -> partial[SqlSalesUnitOfWork]:
    """The factory the sales services get: a fresh unit of work per call."""
    return partial(SqlSalesUnitOfWork, session_factory, public_base_url=public_base_url)
