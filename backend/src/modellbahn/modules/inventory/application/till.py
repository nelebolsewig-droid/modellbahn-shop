"""The till (*Kasse*, ADR 0040): SumUp sales book pieces out by themselves.

Every minute the worker fetches the successful card and cash sales of the SumUp app and
keeps each line once. A line whose name is assigned to a variant books the oldest free
pieces of it out as sold, at the till's price and on the channel *Messe* (on a day a
fair runs) or *Laden*. Lines nobody can book by themselves wait in the Stellwerk:
names not yet assigned, prices typed in without an article, and pieces sold but not
(yet) on a shelf. Assigning a name books its waiting lines at once.

Fetching starts the first time it runs: earlier sales were booked out by hand.
"""

from dataclasses import dataclass, field, replace
from datetime import datetime, time, timedelta
from typing import Final
from uuid import UUID
from zoneinfo import ZoneInfo

import structlog

from modellbahn.modules.catalog.contracts.variants import SaleVariant
from modellbahn.modules.inventory.application.common import Journal, UnitOfWorkFactory, lock_oldest
from modellbahn.modules.inventory.application.ports import InventoryUnitOfWork, TillGateway
from modellbahn.modules.inventory.domain.errors import (
    InvalidFieldError,
    TillLineNotFoundError,
    TillUnavailableError,
    VariantNotFoundError,
)
from modellbahn.modules.inventory.domain.model import (
    Sale,
    SaleChannel,
    ScrapReason,
    UnitStatus,
)
from modellbahn.modules.inventory.domain.till import (
    OPEN_STATES,
    TILL_NAME_MAX_LENGTH,
    TillItem,
    TillLine,
    TillLineState,
    TillProduct,
    TillSale,
    TillState,
    is_custom_amount,
    line_state,
    till_key,
)
from modellbahn.platform.clock import Clock
from modellbahn.platform.ids import new_id

_logger = structlog.get_logger(__name__)

SHOP_TIME_ZONE: Final = ZoneInfo("Europe/Berlin")
LOOKBACK: Final = timedelta(days=3)
"""How far back each run asks: a card reader that was offline reports its sales late."""
OPEN_LIST_MAX: Final = 200
ERROR_MAX_LENGTH: Final = 300


@dataclass(frozen=True, slots=True)
class TillLineView:
    line: TillLine
    variant: SaleVariant | None
    """The variant its name is assigned to, if any."""


@dataclass(frozen=True, slots=True)
class TillItemView:
    item: TillItem
    variant: SaleVariant | None


@dataclass(frozen=True, slots=True)
class TillOverview:
    enabled: bool
    """Whether the worker fetches the till's sales (SumUp is configured)."""
    state: TillState | None
    """``None`` until the first fetch."""
    open: list[TillLineView]
    """What somebody still has to look at, newest first."""
    items: list[TillItemView]
    """Every name assigned so far, by name."""
    booked_today: int = 0
    """Pieces the till booked out today by itself."""


@dataclass(slots=True)
class _Booking:
    """Shared by the lines booked in one transaction: the journal and the channels by day."""

    journal: Journal
    channels: dict[str, SaleChannel] = field(default_factory=dict)


def shop_day_start(at: datetime) -> datetime:
    local = at.astimezone(SHOP_TIME_ZONE)
    return datetime.combine(local.date(), time(), tzinfo=SHOP_TIME_ZONE)


class TillService:
    def __init__(
        self,
        *,
        uow_factory: UnitOfWorkFactory,
        clock: Clock,
        gateway: TillGateway | None = None,
        enabled: bool | None = None,
    ) -> None:
        self._uow = uow_factory
        self._clock = clock
        self._gateway = gateway
        self._enabled = gateway is not None if enabled is None else enabled

    # --- Fetching -----------------------------------------------------------------------

    async def sync(self) -> int:
        """Fetch the till's new sales and book them; returns the number of new lines."""
        if self._gateway is None:
            return 0
        now = self._clock.now()
        async with self._uow() as uow:
            state = await uow.till.state()
            if state is None:
                await uow.till.save_state(TillState(since=now, last_sync_at=now, last_error=""))
                await uow.commit()
                _logger.info("inventory.till.started", since=now.isoformat())
                return 0
        try:
            listed = await self._gateway.sales_since(max(state.since, now - LOOKBACK))
            listed = [sale for sale in listed if sale.sold_at >= state.since]
            async with self._uow() as uow:
                known = await uow.till.known_codes({sale.transaction_code for sale in listed})
            sales = [
                replace(sale, products=await self._gateway.products(sale))
                for sale in listed
                if sale.transaction_code not in known
            ]
        except TillUnavailableError as exc:
            await self._remember_error(str(exc))
            raise
        async with self._uow() as uow:
            # The row lock keeps two workers from booking the same sale twice.
            locked = await uow.till.state(for_update=True)
            if locked is None:  # pragma: no cover - the row is never deleted
                return 0
            known = await uow.till.known_codes({sale.transaction_code for sale in sales})
            new = [sale for sale in sales if sale.transaction_code not in known]
            booking = _Booking(Journal(uow, staff_id=None, now=now))
            keys = {till_key(p.name) for sale in new for p in sale.products}
            items = await uow.till.items(keys) if keys else {}
            added = 0
            for sale in new:
                for position, product in enumerate(sale.products):
                    line = _line_of(sale, position, product, now)
                    await self._book(uow, booking, line, items.get(line.key))
                    await uow.till.add_line(line)
                    added += 1
            # Pieces sold before they were on a shelf: booked as soon as they are.
            waiting = await uow.till.lines({TillLineState.SHORT}, for_update=True)
            if waiting:
                waiting_items = await uow.till.items({line.key for line in waiting})
                for line in waiting:
                    if await self._book(uow, booking, line, waiting_items.get(line.key)):
                        await uow.till.update_line(line)
            locked.last_sync_at = now
            locked.last_error = ""
            await uow.till.save_state(locked)
            await uow.commit()
        if added:
            _logger.info(
                "inventory.till.fetched",
                lines=added,
                booked=len(booking.journal.booked),
            )
        return added

    async def _remember_error(self, message: str) -> None:
        async with self._uow() as uow:
            locked = await uow.till.state(for_update=True)
            if locked is not None:
                locked.last_error = message[:ERROR_MAX_LENGTH]
                await uow.till.save_state(locked)
                await uow.commit()

    # --- In the Stellwerk ---------------------------------------------------------------

    async def overview(self) -> TillOverview:
        now = self._clock.now()
        async with self._uow() as uow:
            state = await uow.till.state()
            open_lines = await uow.till.lines(OPEN_STATES, limit=OPEN_LIST_MAX, newest_first=True)
            items = await uow.till.items()
            today = await uow.till.lines(
                {TillLineState.BOOKED, TillLineState.SHORT}, sold_since=shop_day_start(now)
            )
            variant_ids = {i.variant_id for i in items.values() if i.variant_id is not None}
            variants = await uow.catalog.variants(variant_ids) if variant_ids else {}
        return TillOverview(
            enabled=self._enabled,
            state=state,
            open=[
                TillLineView(line=line, variant=_variant_of(items.get(line.key), variants))
                for line in open_lines
            ],
            items=sorted(
                (
                    TillItemView(item=item, variant=_variant_of(item, variants))
                    for item in items.values()
                ),
                key=lambda view: view.item.key,
            ),
            booked_today=sum(line.booked for line in today),
        )

    async def assign(
        self,
        name: str,
        *,
        variant_id: UUID | None,
        ignored: bool,
        staff_id: UUID | None,
    ) -> TillOverview:
        """Say what the till's ``name`` sells (or that it is no model, or not yet known);
        its waiting lines are booked at once."""
        shown = " ".join(name.split())
        if is_custom_amount(shown):
            raise InvalidFieldError("name", "custom_amount", "a price without an article")
        if len(shown) > TILL_NAME_MAX_LENGTH:
            raise InvalidFieldError("name", "too_long", f"at most {TILL_NAME_MAX_LENGTH}")
        if ignored and variant_id is not None:
            raise InvalidFieldError("variant_id", "with_ignored", "a variant or ignored")
        now = self._clock.now()
        async with self._uow() as uow:
            if variant_id is not None and not await uow.catalog.variants([variant_id]):
                raise VariantNotFoundError
            item = TillItem(
                key=till_key(shown),
                name=shown,
                variant_id=variant_id,
                ignored=ignored,
                assigned_by=staff_id,
                updated_at=now,
            )
            await uow.till.save_item(item)
            booking = _Booking(Journal(uow, staff_id=staff_id, now=now))
            waiting = await uow.till.lines(
                {TillLineState.UNASSIGNED, TillLineState.SHORT}, key=item.key, for_update=True
            )
            for line in waiting:
                if await self._book(uow, booking, line, item):
                    await uow.till.update_line(line)
            await uow.commit()
        _logger.info(
            "inventory.till.assigned",
            name=shown,
            variant=str(variant_id) if variant_id else None,
            ignored=ignored,
            lines=len(waiting),
        )
        return await self.overview()

    async def settle(self, line_id: UUID) -> TillOverview:
        """A waiting line was taken care of by hand (booked out in the Stellwerk)."""
        async with self._uow() as uow:
            line = await uow.till.line(line_id, for_update=True)
            if line is None:
                raise TillLineNotFoundError
            if line.state in OPEN_STATES:
                line.state = TillLineState.DONE
                line.updated_at = self._clock.now()
                await uow.till.update_line(line)
                await uow.commit()
        return await self.overview()

    # --- Booking ------------------------------------------------------------------------

    async def _book(
        self,
        uow: InventoryUnitOfWork,
        booking: _Booking,
        line: TillLine,
        item: TillItem | None,
    ) -> bool:
        """Book as many of the line's missing pieces as are free; whether it changed."""
        before = (line.booked, line.state)
        variant_id = item.variant_id if item is not None and not item.ignored else None
        if variant_id is not None and line.missing > 0 and not is_custom_amount(line.name):
            units = await lock_oldest(
                uow, variant_id, UnitStatus.IN_STOCK, limit=line.missing, location=None
            )
            if units:
                sale = Sale(
                    channel=await _channel(uow, booking, line.sold_at),
                    price_cents=line.unit_price_cents,
                )
                note = f"SumUp-Kasse, Beleg {line.transaction_code}"
                for unit in units:
                    movement = unit.scrap(note, booking.journal.now, ScrapReason.SOLD, sale)
                    await booking.journal.book(unit, movement)
                line.booked += len(units)
        line.state = line_state(
            line.name,
            assigned=variant_id is not None,
            ignored=item is not None and item.ignored,
            quantity=line.quantity,
            booked=line.booked,
        )
        changed = (line.booked, line.state) != before
        if changed:
            line.updated_at = booking.journal.now
        return changed


async def _channel(uow: InventoryUnitOfWork, booking: _Booking, sold_at: datetime) -> SaleChannel:
    """*Messe* on a day a fair runs, else *Laden*."""
    day = sold_at.astimezone(SHOP_TIME_ZONE).date()
    cached = booking.channels.get(day.isoformat())
    if cached is None:
        cached = SaleChannel.FAIR if await uow.fairs.fair_on(day) else SaleChannel.STORE
        booking.channels[day.isoformat()] = cached
    return cached


def _line_of(sale: TillSale, position: int, product: TillProduct, now: datetime) -> TillLine:
    shown = " ".join(product.name.split())[:TILL_NAME_MAX_LENGTH]
    return TillLine(
        id=new_id(),
        transaction_code=sale.transaction_code,
        position=position,
        sold_at=sale.sold_at,
        payment=sale.payment,
        name=shown,
        key=till_key(shown),
        quantity=product.quantity,
        unit_price_cents=product.unit_price_cents,
        booked=0,
        state=TillLineState.UNASSIGNED,
        updated_at=now,
    )


def _variant_of(item: TillItem | None, variants: dict[UUID, SaleVariant]) -> SaleVariant | None:
    if item is None or item.variant_id is None:
        return None
    return variants.get(item.variant_id)
