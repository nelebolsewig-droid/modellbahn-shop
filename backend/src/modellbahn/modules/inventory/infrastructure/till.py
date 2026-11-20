"""The till (ADR 0040): its tables, and SumUp's transactions behind the ``TillGateway`` port.

SumUp's model stays in this file (KONZEPT §2.6). What the SumUp app rings up arrives in
the Transactions API (``/v2.1/merchants/{code}/transactions``) as payment type ``POS``
(card) or ``CASH``; the shop's own online payments are ``ECOM`` or ``APM`` and are left
out. The list has no products; each new sale is asked for once by its code.
"""

from collections.abc import Collection
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any, Final, Self
from urllib.parse import parse_qsl
from uuid import UUID

import httpx
import structlog
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from modellbahn.modules.inventory.domain.errors import InvalidFieldError, TillUnavailableError
from modellbahn.modules.inventory.domain.till import (
    TILL_QUANTITY_MAX,
    TillItem,
    TillLine,
    TillLineState,
    TillPayment,
    TillProduct,
    TillSale,
    TillState,
)
from modellbahn.modules.inventory.infrastructure.tables import till_items, till_lines, till_state
from modellbahn.modules.site.contracts.fairs import load_fair_on
from modellbahn.platform.config import Settings
from modellbahn.platform.uow import UnitOfWork

_logger = structlog.get_logger(__name__)

_STATE_ID: Final = 1


class SqlTillRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def state(self, *, for_update: bool = False) -> TillState | None:
        statement = select(
            till_state.c.since, till_state.c.last_sync_at, till_state.c.last_error
        ).where(till_state.c.id == _STATE_ID)
        if for_update:
            statement = statement.with_for_update()
        row = (await self._session.execute(statement)).one_or_none()
        return None if row is None else TillState(*row)

    async def save_state(self, state: TillState) -> None:
        values = {
            "since": state.since,
            "last_sync_at": state.last_sync_at,
            "last_error": state.last_error,
        }
        await self._session.execute(
            insert(till_state)
            .values(id=_STATE_ID, **values)
            .on_conflict_do_update(index_elements=[till_state.c.id], set_=values)
        )

    async def known_codes(self, codes: Collection[str]) -> set[str]:
        if not codes:
            return set()
        rows = await self._session.execute(
            select(till_lines.c.transaction_code)
            .where(till_lines.c.transaction_code.in_(list(codes)))
            .distinct()
        )
        return set(rows.scalars())

    async def add_line(self, line: TillLine) -> None:
        await self._session.execute(insert(till_lines).values(**_line_values(line)))

    async def update_line(self, line: TillLine) -> None:
        values = _line_values(line)
        del values["id"]
        await self._session.execute(
            update(till_lines).where(till_lines.c.id == line.id).values(**values)
        )

    async def line(self, line_id: UUID, *, for_update: bool = False) -> TillLine | None:
        statement = select(*till_lines.c).where(till_lines.c.id == line_id)
        if for_update:
            statement = statement.with_for_update()
        row = (await self._session.execute(statement)).one_or_none()
        return None if row is None else TillLine(**row._mapping)

    async def lines(
        self,
        states: Collection[TillLineState],
        *,
        key: str | None = None,
        sold_since: datetime | None = None,
        limit: int | None = None,
        newest_first: bool = False,
        for_update: bool = False,
    ) -> list[TillLine]:
        statement = select(*till_lines.c).where(till_lines.c.state.in_(list(states)))
        if key is not None:
            statement = statement.where(till_lines.c.key == key)
        if sold_since is not None:
            statement = statement.where(till_lines.c.sold_at >= sold_since)
        order = (till_lines.c.sold_at, till_lines.c.transaction_code, till_lines.c.position)
        statement = statement.order_by(*(c.desc() for c in order) if newest_first else order)
        if limit is not None:
            statement = statement.limit(limit)
        if for_update:
            statement = statement.with_for_update()
        rows = await self._session.execute(statement)
        return [TillLine(**row._mapping) for row in rows]

    async def items(self, keys: Collection[str] | None = None) -> dict[str, TillItem]:
        statement = select(*till_items.c)
        if keys is not None:
            if not keys:
                return {}
            statement = statement.where(till_items.c.key.in_(list(keys)))
        rows = await self._session.execute(statement)
        return {row.key: TillItem(**row._mapping) for row in rows}

    async def save_item(self, item: TillItem) -> None:
        values = {
            "name": item.name,
            "variant_id": item.variant_id,
            "ignored": item.ignored,
            "assigned_by": item.assigned_by,
            "updated_at": item.updated_at,
        }
        await self._session.execute(
            insert(till_items)
            .values(key=item.key, **values)
            .on_conflict_do_update(index_elements=[till_items.c.key], set_=values)
        )


def _line_values(line: TillLine) -> dict[str, Any]:
    return {
        "id": line.id,
        "transaction_code": line.transaction_code,
        "position": line.position,
        "sold_at": line.sold_at,
        "payment": line.payment,
        "name": line.name,
        "key": line.key,
        "quantity": line.quantity,
        "unit_price_cents": line.unit_price_cents,
        "booked": line.booked,
        "state": line.state,
        "updated_at": line.updated_at,
    }


class SqlFairs:
    """The site module's fairs, inside this unit of work's transaction."""

    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    async def fair_on(self, day: date) -> str | None:
        return await load_fair_on(self._uow, day)


# --- SumUp ------------------------------------------------------------------------------

_PAYMENTS: Final = {"POS": TillPayment.CARD, "CASH": TillPayment.CASH}
_PAGE_SIZE: Final = 100
_MAX_PAGES: Final = 30
_CUSTOM_AMOUNT: Final = "Individueller Betrag"


class SumUpTill:
    """The SumUp app's sales, read with the merchant's API key (``transactions.history``)."""

    def __init__(
        self,
        *,
        api_key: str,
        merchant_code: str,
        base_url: str = "https://api.sumup.com",
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._path = f"/v2.1/merchants/{merchant_code}/transactions"
        self._client = httpx.AsyncClient(
            base_url=base_url,
            headers={"Authorization": f"Bearer {api_key}", "Accept": "application/json"},
            timeout=httpx.Timeout(20.0),
            transport=transport,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()

    async def sales_since(self, since: datetime) -> list[TillSale]:
        params: dict[str, str] = {
            "oldest_time": since.astimezone(UTC).isoformat(timespec="seconds"),
            "order": "ascending",
            "limit": str(_PAGE_SIZE),
        }
        sales: list[TillSale] = []
        for _ in range(_MAX_PAGES):
            page = await self._get(f"{self._path}/history", params)
            for item in page.get("items") or []:
                sale = _listed_sale(item)
                if sale is not None:
                    sales.append(sale)
            following = _next_params(page)
            if following is None:
                break
            params = following
        else:
            _logger.warning("inventory.till.too_many_pages", pages=_MAX_PAGES)
        return sales

    async def products(self, sale: TillSale) -> tuple[TillProduct, ...]:
        detail = await self._get(self._path, {"transaction_code": sale.transaction_code})
        products = tuple(
            product
            for raw in detail.get("products") or []
            if isinstance(raw, dict) and (product := _product(raw)) is not None
        )
        if products:
            return products
        return (TillProduct(name=_CUSTOM_AMOUNT, quantity=1, unit_price_cents=sale.total_cents),)

    async def _get(self, path: str, params: dict[str, str]) -> dict[str, Any]:
        try:
            response = await self._client.get(path, params=params)
        except httpx.HTTPError as exc:
            _logger.warning("inventory.till.unreachable", error=type(exc).__name__)
            raise TillUnavailableError("SumUp ist nicht erreichbar.") from exc
        if response.status_code >= 400:  # noqa: PLR2004
            _logger.error("inventory.till.error", status=response.status_code, path=path)
            if response.status_code in {401, 403}:
                raise TillUnavailableError(
                    "SumUp lehnt den Zugriff ab: Der API-Schlüssel darf keine Umsätze lesen."
                )
            raise TillUnavailableError(f"SumUp antwortet mit Fehler {response.status_code}.")
        data = response.json()
        return data if isinstance(data, dict) else {}


def _listed_sale(item: Any) -> TillSale | None:
    """A successful card or cash payment of the SumUp app; ``None`` for anything else."""
    if not isinstance(item, dict):
        return None
    payment = _PAYMENTS.get(str(item.get("payment_type") or ""))
    code = str(item.get("transaction_code") or "")
    if (
        payment is None
        or not code
        or item.get("type") != "PAYMENT"
        or item.get("status") != "SUCCESSFUL"
    ):
        return None
    try:
        sold_at = datetime.fromisoformat(str(item.get("timestamp")))
    except ValueError:
        return None
    if sold_at.tzinfo is None:
        sold_at = sold_at.replace(tzinfo=UTC)
    return TillSale(
        transaction_code=code,
        sold_at=sold_at.astimezone(UTC),
        payment=payment,
        total_cents=_cents(item.get("amount")) or 0,
        products=(),
    )


def _product(raw: dict[str, Any]) -> TillProduct | None:
    """A product line: gross per piece from the total with VAT (or the total, without)."""
    try:
        quantity = int(Decimal(str(raw.get("quantity") or 1)).to_integral_value(ROUND_HALF_UP))
    except InvalidOperation:
        quantity = 1
    quantity = min(max(quantity, 1), TILL_QUANTITY_MAX)
    total = _cents(raw.get("total_with_vat"))
    if total is None:
        total = _cents(raw.get("total_price"))
    if total is None:
        unit = _cents(raw.get("price_with_vat"))
        unit = unit if unit is not None else _cents(raw.get("price"))
        total = (unit or 0) * quantity
    try:
        return TillProduct(
            name=str(raw.get("name") or ""),
            quantity=quantity,
            unit_price_cents=max(round(total / quantity), 0),
        )
    except InvalidFieldError:
        return None


def _cents(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int((Decimal(str(value)) * 100).to_integral_value(ROUND_HALF_UP))
    except InvalidOperation:
        return None


def _next_params(page: dict[str, Any]) -> dict[str, str] | None:
    """The next page: SumUp links it as a query string for the same endpoint."""
    for link in page.get("links") or []:
        if isinstance(link, dict) and link.get("rel") == "next" and link.get("href"):
            return dict(parse_qsl(str(link["href"]).lstrip("?")))
    return None


def build_till(settings: Settings) -> SumUpTill:
    """The SumUp app's sales with the shop's key (check ``settings.till_enabled`` first)."""
    return SumUpTill(
        api_key=settings.sumup_api_key.get_secret_value(),
        merchant_code=settings.sumup_merchant_code,
        base_url=settings.sumup_api_url,
    )
