"""The till (ADR 0040): names, line states, and SumUp's transactions read right.

The answers below follow what SumUp returned for the shop's account (anonymised): the
SumUp app's sales as ``POS`` (card) and ``CASH``, the shop's online payments as ``ECOM``
and ``APM``, products with gross totals, and none of our article numbers.
"""

from datetime import UTC, datetime
from typing import Any

import httpx
import pytest

from modellbahn.modules.inventory.domain.errors import InvalidFieldError, TillUnavailableError
from modellbahn.modules.inventory.domain.till import (
    TillLineState,
    TillPayment,
    TillProduct,
    TillSale,
    is_custom_amount,
    line_state,
    till_key,
)
from modellbahn.modules.inventory.infrastructure.till import SumUpTill

MERCHANT = "MTEST123"
HISTORY = f"/v2.1/merchants/{MERCHANT}/transactions/history"
DETAIL = f"/v2.1/merchants/{MERCHANT}/transactions"


def listed(code: str, payment_type: str, **changes: Any) -> dict[str, Any]:
    return {
        "transaction_code": code,
        "payment_type": payment_type,
        "type": "PAYMENT",
        "status": "SUCCESSFUL",
        "timestamp": "2026-10-03T11:17:21.884Z",
        "amount": 345.0,
        "product_summary": "…",
        **changes,
    }


PAGE_ONE: dict[str, Any] = {
    "items": [
        listed("TCARD", "POS"),
        listed("TCASH", "CASH", timestamp="2026-10-03T14:06:36.198Z", amount=25.0),
        listed("TSHOP", "ECOM"),
        listed("TPAYPAL", "APM"),
        listed("TFAILED", "POS", status="FAILED"),
        listed("TREFUND", "POS", type="REFUND", status="REFUNDED"),
    ],
    "links": [{"rel": "next", "href": "limit=100&order=ascending&oldest_ref=abc"}],
}
PAGE_TWO: dict[str, Any] = {"items": [listed("TLATE", "POS", amount=60)], "links": []}
DETAILS: dict[str, dict[str, Any]] = {
    "TCARD": {
        "products": [
            # Without VAT in SumUp: only the total.
            {"name": "Straßenbahnzug TTm", "price": 185, "quantity": 1, "total_price": 185},
            # With VAT: the gross total counts.
            {
                "name": "Edk6 tt",
                "price": 168.07,
                "price_with_vat": 200,
                "quantity": 2,
                "total_price": 336.13,
                "total_with_vat": 400,
            },
        ]
    },
    "TCASH": {"products": []},
}


def transport(seen: list[httpx.Request]) -> httpx.MockTransport:
    def answer(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        assert request.headers["Authorization"] == "Bearer sup_sk_test"
        if request.url.path == HISTORY:
            page = PAGE_TWO if request.url.params.get("oldest_ref") else PAGE_ONE
            return httpx.Response(200, json=page)
        if request.url.path == DETAIL:
            return httpx.Response(200, json=DETAILS[request.url.params["transaction_code"]])
        return httpx.Response(404)

    return httpx.MockTransport(answer)


def till(seen: list[httpx.Request], handler: httpx.MockTransport | None = None) -> SumUpTill:
    return SumUpTill(
        api_key="sup_sk_test",
        merchant_code=MERCHANT,
        base_url="https://sumup.test",
        transport=handler or transport(seen),
    )


class TestNames:
    def test_case_and_spacing_do_not_count(self) -> None:
        assert till_key("  EDK 6\tKnickausleger  TT ") == "edk 6 knickausleger tt"

    @pytest.mark.parametrize("name", ["Individueller Betrag", " individueller  betrag", ""])
    def test_a_price_without_article(self, name: str) -> None:
        assert is_custom_amount(name)

    def test_states(self) -> None:
        def state(name: str = "K700", **kw: Any) -> TillLineState:
            given = {"assigned": True, "ignored": False, "quantity": 2, "booked": 2, **kw}
            return line_state(name, **given)

        assert state() is TillLineState.BOOKED
        assert state(booked=1) is TillLineState.SHORT
        assert state(assigned=False, booked=0) is TillLineState.UNASSIGNED
        assert state(ignored=True, assigned=False, booked=0) is TillLineState.IGNORED
        assert state("Individueller Betrag", booked=0) is TillLineState.CUSTOM

    def test_a_product_needs_a_quantity(self) -> None:
        with pytest.raises(InvalidFieldError):
            TillProduct(name="K700", quantity=0, unit_price_cents=100)


class TestSumUp:
    async def test_only_successful_card_and_cash_sales_of_the_app_on_all_pages(self) -> None:
        seen: list[httpx.Request] = []
        async with till(seen) as sumup:
            sales = await sumup.sales_since(datetime(2026, 10, 3, 10, tzinfo=UTC))
        assert [(s.transaction_code, s.payment, s.total_cents) for s in sales] == [
            ("TCARD", TillPayment.CARD, 34500),
            ("TCASH", TillPayment.CASH, 2500),
            ("TLATE", TillPayment.CARD, 6000),
        ]
        assert sales[1].sold_at == datetime(2026, 10, 3, 14, 6, 36, 198000, tzinfo=UTC)
        assert seen[0].url.params["oldest_time"] == "2026-10-03T10:00:00+00:00"
        assert seen[1].url.params["oldest_ref"] == "abc"

    async def test_products_with_their_gross_price_per_piece(self) -> None:
        async with till([]) as sumup:
            products = await sumup.products(sale("TCARD", 34500))
        assert products == (
            TillProduct(name="Straßenbahnzug TTm", quantity=1, unit_price_cents=18500),
            TillProduct(name="Edk6 tt", quantity=2, unit_price_cents=20000),
        )

    async def test_a_sale_without_products_is_its_total(self) -> None:
        async with till([]) as sumup:
            products = await sumup.products(sale("TCASH", 2500))
        assert products == (
            TillProduct(name="Individueller Betrag", quantity=1, unit_price_cents=2500),
        )

    @pytest.mark.parametrize(
        ("status", "message"),
        [
            (403, "SumUp lehnt den Zugriff ab: Der API-Schlüssel darf keine Umsätze lesen."),
            (502, "SumUp antwortet mit Fehler 502."),
        ],
    )
    async def test_refusals_are_unavailable(self, status: int, message: str) -> None:
        refusing = httpx.MockTransport(lambda _: httpx.Response(status, json={}))
        async with till([], refusing) as sumup:
            with pytest.raises(TillUnavailableError, match=message):
                await sumup.sales_since(datetime(2026, 10, 3, tzinfo=UTC))

    async def test_unreachable(self) -> None:
        def fail(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("down", request=request)

        async with till([], httpx.MockTransport(fail)) as sumup:
            with pytest.raises(TillUnavailableError, match="nicht erreichbar"):
                await sumup.sales_since(datetime(2026, 10, 3, tzinfo=UTC))


def sale(code: str, total: int) -> TillSale:
    return TillSale(
        transaction_code=code,
        sold_at=datetime(2026, 10, 3, tzinfo=UTC),
        payment=TillPayment.CARD,
        total_cents=total,
        products=(),
    )
