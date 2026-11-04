"""The SumUp adapter against a fake SumUp API: the requests it makes, the answers it reads."""

import json
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from uuid import UUID

import httpx
import pytest
from pydantic import SecretStr

from modellbahn.modules.sales.application.ports import PaymentRequest
from modellbahn.modules.sales.domain.errors import (
    CheckoutClosedError,
    InvalidFieldError,
    PaymentUnavailableError,
)
from modellbahn.modules.sales.domain.model import PaymentProgress
from modellbahn.modules.sales.infrastructure.payments import (
    ClosedPaymentGateway,
    MockPaymentGateway,
    SumUpPaymentGateway,
    build_payment_gateway,
)
from modellbahn.platform.config import PaymentProvider, Settings

API_KEY = "sup_sk_test_0123456789"
MERCHANT = "MC4K9Z7Q"
PAYMENT_ID = UUID("0193a1f2-7c4e-7d1a-9b2c-3d4e5f607182")
CHECKOUT = "4e425463-3e1b-431d-83fa-1e51c2925e99"
PAGE = f"https://checkout.sumup.com/pay/{CHECKOUT}"

type Handler = Callable[[httpx.Request], httpx.Response]


def request(**changes: object) -> PaymentRequest:
    values: dict[str, object] = {
        "payment_id": PAYMENT_ID,
        "order_number": "MB-2026-00042",
        "amount_cents": 8580,
        "method": "sumup",
        "return_url": "https://neu.adp-modelle.de/bestellung/tok/bezahlen",
        # Due in German summer time; SumUp gets it in UTC.
        "valid_until": datetime(2026, 10, 23, 12, 0, tzinfo=timezone(timedelta(hours=2))),
    }
    values.update(changes)
    return PaymentRequest(**values)  # type: ignore[arg-type]


def gateway(handler: Handler) -> SumUpPaymentGateway:
    return SumUpPaymentGateway(
        api_key=API_KEY,
        merchant_code=MERCHANT,
        notify_url="https://neu.adp-modelle.de/api/v1/webhooks/sumup",
        description="adp-Modelle",
        base_url="https://api.sumup.test",
        transport=httpx.MockTransport(handler),
    )


def answer(body: object, status: int = 200) -> Handler:
    def handle(_: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json=body)

    return handle


class TestBegin:
    async def test_creates_a_hosted_checkout(self) -> None:
        seen: list[httpx.Request] = []

        def handle(incoming: httpx.Request) -> httpx.Response:
            seen.append(incoming)
            return httpx.Response(
                201,
                json={"id": CHECKOUT, "status": "PENDING", "hosted_checkout_url": PAGE},
            )

        start = await gateway(handle).begin(request())

        assert (start.provider, start.provider_ref, start.checkout_url) == ("sumup", CHECKOUT, PAGE)
        assert start.result is None
        (sent,) = seen
        assert (sent.method, sent.url.path) == ("POST", "/v0.1/checkouts")
        assert sent.headers["authorization"] == f"Bearer {API_KEY}"
        assert json.loads(sent.content) == {
            "checkout_reference": PAYMENT_ID.hex,
            "amount": 85.8,
            "currency": "EUR",
            "merchant_code": MERCHANT,
            "description": "adp-Modelle MB-2026-00042",
            "return_url": "https://neu.adp-modelle.de/api/v1/webhooks/sumup",
            "redirect_url": "https://neu.adp-modelle.de/bestellung/tok/bezahlen",
            "valid_until": "2026-10-23T10:00:00+00:00",
            "hosted_checkout": {"enabled": True},
        }

    async def test_only_the_sumup_method(self) -> None:
        with pytest.raises(InvalidFieldError):
            await gateway(answer({})).begin(request(method="succeeds"))

    @pytest.mark.parametrize(
        "body",
        [
            {"id": CHECKOUT},
            {"hosted_checkout_url": PAGE},
            {"id": CHECKOUT, "hosted_checkout_url": "http://checkout.sumup.com/pay/x"},
        ],
    )
    async def test_an_incomplete_checkout_is_no_page(self, body: dict[str, str]) -> None:
        with pytest.raises(PaymentUnavailableError):
            await gateway(answer(body, 201)).begin(request())

    @pytest.mark.parametrize("status", [400, 401, 409, 500, 503])
    async def test_errors_charge_nothing(self, status: int) -> None:
        body = {"error_code": "DUPLICATED_CHECKOUT", "message": "Checkout already exists"}
        with pytest.raises(PaymentUnavailableError):
            await gateway(answer(body, status)).begin(request())

    async def test_an_unreachable_sumup_charges_nothing(self) -> None:
        def handle(incoming: httpx.Request) -> httpx.Response:
            raise httpx.ConnectTimeout("too slow", request=incoming)

        with pytest.raises(PaymentUnavailableError):
            await gateway(handle).begin(request())


class TestOutcome:
    async def test_paid_names_the_successful_transaction(self) -> None:
        seen: list[httpx.Request] = []

        def handle(incoming: httpx.Request) -> httpx.Response:
            seen.append(incoming)
            return httpx.Response(
                200,
                json={
                    "id": CHECKOUT,
                    "status": "PAID",
                    "transactions": [
                        {"id": "txn_failed", "status": "FAILED"},
                        {"id": "txn_ok", "status": "SUCCESSFUL"},
                    ],
                },
            )

        outcome = await gateway(handle).outcome(CHECKOUT)
        assert (outcome.progress, outcome.transaction_ref) == (PaymentProgress.CAPTURED, "txn_ok")
        assert (seen[0].method, seen[0].url.path) == ("GET", f"/v0.1/checkouts/{CHECKOUT}")

    async def test_paid_without_transactions(self) -> None:
        outcome = await gateway(answer({"status": "PAID"})).outcome(CHECKOUT)
        assert (outcome.progress, outcome.transaction_ref) == (PaymentProgress.CAPTURED, None)

    async def test_expired_is_over(self) -> None:
        outcome = await gateway(answer({"status": "EXPIRED"})).outcome(CHECKOUT)
        assert (outcome.progress, outcome.failure_code) == (PaymentProgress.FAILED, "expired")

    @pytest.mark.parametrize("status", ["PENDING", "FAILED", "SOMETHING_NEW", None])
    async def test_anything_else_stays_open(self, status: str | None) -> None:
        # A failed attempt may be repeated on the same page.
        outcome = await gateway(answer({"status": status})).outcome(CHECKOUT)
        assert outcome.progress is PaymentProgress.PENDING

    async def test_a_list_is_no_answer(self) -> None:
        outcome = await gateway(answer([])).outcome(CHECKOUT)
        assert outcome.progress is PaymentProgress.PENDING


class TestAbandonAndRefund:
    async def test_abandon_deactivates_the_checkout(self) -> None:
        seen: list[httpx.Request] = []

        def handle(incoming: httpx.Request) -> httpx.Response:
            seen.append(incoming)
            return httpx.Response(200, json={"id": CHECKOUT, "status": "EXPIRED"})

        await gateway(handle).abandon(CHECKOUT)
        assert (seen[0].method, seen[0].url.path) == ("DELETE", f"/v0.1/checkouts/{CHECKOUT}")

    async def test_a_used_page_cannot_be_abandoned(self) -> None:
        with pytest.raises(PaymentUnavailableError):
            await gateway(answer({"error_code": "CONFLICT"}, 409)).abandon(CHECKOUT)

    async def test_refund_names_the_transaction(self) -> None:
        seen: list[httpx.Request] = []

        def handle(incoming: httpx.Request) -> httpx.Response:
            seen.append(incoming)
            return httpx.Response(204)

        await gateway(handle).refund(refund_ref="txn_ok", amount_cents=8580)
        (sent,) = seen
        assert (sent.method, sent.url.path) == (
            "POST",
            f"/v1.0/merchants/{MERCHANT}/payments/txn_ok/refunds",
        )
        # Without a body SumUp refunds all of it.
        assert sent.content == b""

    async def test_a_failed_refund_raises(self) -> None:
        with pytest.raises(PaymentUnavailableError):
            await gateway(answer("not json", 500)).refund(refund_ref="txn_ok", amount_cents=1)


class TestOtherProviders:
    async def test_the_test_payment_answers_at_once(self) -> None:
        mock = MockPaymentGateway()
        assert mock.takes_payments
        start = await mock.begin(request(method="succeeds"))
        assert start.result is not None
        assert start.result.captured
        declined = await mock.begin(request(method="declined"))
        assert declined.result is not None
        assert declined.result.failure_code == "declined"
        with pytest.raises(PaymentUnavailableError):
            await mock.begin(request(method="fails"))
        with pytest.raises(InvalidFieldError):
            await mock.begin(request(method="sumup"))
        assert (await mock.outcome("mock_1")).progress is PaymentProgress.FAILED
        await mock.abandon("mock_1")
        await mock.refund(refund_ref="mock_1", amount_cents=100)
        await mock.aclose()

    async def test_no_provider_takes_nothing(self) -> None:
        closed = ClosedPaymentGateway()
        assert not closed.takes_payments
        with pytest.raises(CheckoutClosedError):
            await closed.begin(request())
        with pytest.raises(PaymentUnavailableError):
            await closed.outcome("x")
        with pytest.raises(PaymentUnavailableError):
            await closed.abandon("x")
        with pytest.raises(PaymentUnavailableError):
            await closed.refund(refund_ref="x", amount_cents=1)
        await closed.aclose()

    async def test_the_settings_choose_the_provider(self) -> None:
        assert isinstance(build_payment_gateway(Settings()), MockPaymentGateway)
        off = Settings(payment_provider=PaymentProvider.OFF)
        assert isinstance(build_payment_gateway(off), ClosedPaymentGateway)
        sumup = build_payment_gateway(
            Settings(
                payment_provider=PaymentProvider.SUMUP,
                sumup_api_key=SecretStr(API_KEY),
                sumup_merchant_code=MERCHANT,
                public_base_url="https://neu.adp-modelle.de",
            )
        )
        assert isinstance(sumup, SumUpPaymentGateway)
        assert sumup.provider == "sumup"
        await sumup.aclose()
