"""Facade for the sales report (ADR 0039): pieces booked out as sold outside the online shop.

A piece counts once it lies scrapped with the reason ``sold``; when that happened is its
last *Ausbuchen* in the journal. Booked in again or undone, it no longer counts.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select

from modellbahn.modules.inventory.domain.model import (
    MovementReason,
    SaleChannel,
    ScrapReason,
    UnitStatus,
)
from modellbahn.modules.inventory.infrastructure.tables import stock_ledger, units
from modellbahn.platform.uow import UnitOfWork

__all__ = ["OffSiteSale", "SaleChannel", "load_off_site_sales"]


@dataclass(frozen=True, slots=True)
class OffSiteSale:
    """One piece sold at a fair, on site or privately."""

    unit_code: str
    variant_id: UUID
    sold_at: datetime
    channel: SaleChannel | None
    """Empty when nobody said where (booked out before it was asked)."""
    price_cents: int | None
    """Empty while nobody entered it: the report counts the shop price."""
    note: str
    staff_id: UUID | None


async def load_off_site_sales(
    uow: UnitOfWork, since: datetime, until: datetime
) -> Sequence[OffSiteSale]:
    """The pieces booked out as sold in ``[since, until)``, the latest first."""
    last_scrap_id = (
        select(func.max(stock_ledger.c.id).label("id"))
        .where(stock_ledger.c.reason == MovementReason.SCRAP)
        .group_by(stock_ledger.c.unit_id)
        .subquery()
    )
    last_scrap = (
        select(
            stock_ledger.c.unit_id,
            stock_ledger.c.occurred_at,
            stock_ledger.c.staff_id,
        )
        .join(last_scrap_id, last_scrap_id.c.id == stock_ledger.c.id)
        .subquery()
    )
    rows = await uow.session.execute(
        select(
            units.c.code,
            units.c.variant_id,
            units.c.sale_channel,
            units.c.sale_price_cents,
            units.c.scrap_note,
            last_scrap.c.occurred_at,
            last_scrap.c.staff_id,
        )
        .join(last_scrap, last_scrap.c.unit_id == units.c.id)
        .where(
            units.c.status == UnitStatus.SCRAPPED,
            units.c.scrap_reason == ScrapReason.SOLD,
            last_scrap.c.occurred_at >= since,
            last_scrap.c.occurred_at < until,
        )
        .order_by(last_scrap.c.occurred_at.desc(), units.c.code)
    )
    return [
        OffSiteSale(
            unit_code=row.code,
            variant_id=row.variant_id,
            sold_at=row.occurred_at,
            channel=row.sale_channel,
            price_cents=row.sale_price_cents,
            note=row.scrap_note,
            staff_id=row.staff_id,
        )
        for row in rows
    ]
