"""Payment providers behind the ``PaymentGateway`` port (ADR 0019).

* :class:`MockPaymentGateway`: the test payment; the customer chooses the outcome.
* :class:`SumUpPaymentGateway`: SumUp Online with its Hosted Checkout; the customer pays
  on SumUp's page (card, Apple Pay, Google Pay) and comes back to the shop.
* :class:`ClosedPaymentGateway`: no provider; the shop takes no orders.

Each provider's model of payments and errors stays in this file and never reaches the
domain (KONZEPT §2.6).
"""

from datetime import UTC
from decimal import Decimal
from enum import StrEnum
from typing import Any, Final

import httpx
import structlog

from modellbahn.modules.sales.application.ports import PaymentGateway, PaymentRequest
from modellbahn.modules.sales.domain.errors import (
    CheckoutClosedError,
    InvalidFieldError,
    PaymentUnavailableError,
)
from modellbahn.modules.sales.domain.model import (
    ChargeResult,
    PaymentOutcome,
    PaymentProgress,
    PaymentStart,
)
from modellbahn.platform.config import PaymentProvider, Settings
from modellbahn.platform.ids import new_id

_logger = structlog.get_logger(__name__)


class MockScenario(StrEnum):
    """What the mock provider does; the shop's test payment page lets the customer choose."""

    SUCCEEDS = "succeeds"
    DECLINED = "declined"
    FAILS = "fails"
    """The provider cannot be reached: nothing is charged, the customer may try again."""


class MockPaymentGateway:
    """Answers at once with the outcome the payment method names. Charges nothing."""

    PROVIDER: Final = "mock"

    @property
    def provider(self) -> str:
        return self.PROVIDER

    @property
    def takes_payments(self) -> bool:
        return True

    async def begin(self, request: PaymentRequest) -> PaymentStart:
        try:
            scenario = MockScenario(request.method)
        except ValueError:
            raise InvalidFieldError("method", "unknown", "not a payment method") from None
        _logger.info(
            "sales.mock_payment",
            order=request.order_number,
            amount_cents=request.amount_cents,
            scenario=scenario,
        )
        reference = f"mock_{new_id().hex}"
        match scenario:
            case MockScenario.SUCCEEDS:
                result = ChargeResult(captured=True, provider=self.PROVIDER, provider_ref=reference)
            case MockScenario.DECLINED:
                result = ChargeResult(
                    captured=False,
                    provider=self.PROVIDER,
                    provider_ref=reference,
                    failure_code="declined",
                )
            case MockScenario.FAILS:
                raise PaymentUnavailableError
        return PaymentStart(provider=self.PROVIDER, provider_ref=reference, result=result)

    async def outcome(self, provider_ref: str) -> PaymentOutcome:
        # The test payment is settled at once; it never waits on a page.
        return PaymentOutcome(progress=PaymentProgress.FAILED, failure_code="unknown")

    async def abandon(self, provider_ref: str) -> None:
        # Nothing waits on a page.
        return

    async def refund(self, *, refund_ref: str, amount_cents: int) -> None:
        _logger.info("sales.mock_refund", provider_ref=refund_ref, amount_cents=amount_cents)

    async def aclose(self) -> None:
        return


class ClosedPaymentGateway:
    """No provider is connected (``MB_PAYMENT_PROVIDER=off``): nothing can be paid."""

    PROVIDER: Final = "off"

    @property
    def provider(self) -> str:
        return self.PROVIDER

    @property
    def takes_payments(self) -> bool:
        return False

    async def begin(self, request: PaymentRequest) -> PaymentStart:
        raise CheckoutClosedError

    async def outcome(self, provider_ref: str) -> PaymentOutcome:
        raise PaymentUnavailableError

    async def abandon(self, provider_ref: str) -> None:
        raise PaymentUnavailableError

    async def refund(self, *, refund_ref: str, amount_cents: int) -> None:
        raise PaymentUnavailableError

    async def aclose(self) -> None:
        return


def _amount(cents: int) -> float:
    """Major units as SumUp expects them: 85.80 for 8580 cents."""
    return float(Decimal(cents) / 100)


class SumUpPaymentGateway:
    """SumUp Online with its Hosted Checkout (API reference: SumUp's official SDK).

    A checkout is created with ``hosted_checkout.enabled``; its ``hosted_checkout_url`` is
    the page the customer pays on. SumUp brings the customer back to ``redirect_url`` and
    posts the checkout's id to ``return_url``. Neither is trusted: the shop asks SumUp for
    the checkout's state (``GET /v0.1/checkouts/{id}``) before it books anything. A failed
    attempt stays open, since the customer may try again on the same page; only an expired
    checkout is over.
    """

    PROVIDER: Final = "sumup"
    METHOD: Final = "sumup"
    """The one payment method: the customer chooses card or wallet on SumUp's page."""

    def __init__(
        self,
        *,
        api_key: str,
        merchant_code: str,
        notify_url: str,
        description: str,
        base_url: str = "https://api.sumup.com",
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._merchant_code = merchant_code
        self._notify_url = notify_url
        self._description = description
        self._client = httpx.AsyncClient(
            base_url=base_url,
            headers={"Authorization": f"Bearer {api_key}", "Accept": "application/json"},
            timeout=httpx.Timeout(15.0),
            transport=transport,
        )

    @property
    def provider(self) -> str:
        return self.PROVIDER

    @property
    def takes_payments(self) -> bool:
        return True

    async def aclose(self) -> None:
        await self._client.aclose()

    async def begin(self, request: PaymentRequest) -> PaymentStart:
        if request.method != self.METHOD:
            raise InvalidFieldError("method", "unknown", "not a payment method")
        body = {
            # Our id of the attempt: SumUp refuses a second checkout with the same one.
            "checkout_reference": request.payment_id.hex,
            "amount": _amount(request.amount_cents),
            "currency": "EUR",
            "merchant_code": self._merchant_code,
            "description": f"{self._description} {request.order_number}",
            "return_url": self._notify_url,
            "redirect_url": request.return_url,
            "valid_until": request.valid_until.astimezone(UTC).isoformat(timespec="seconds"),
            "hosted_checkout": {"enabled": True},
        }
        checkout = await self._call("POST", "/v0.1/checkouts", json=body)
        checkout_id = str(checkout.get("id") or "")
        page = str(checkout.get("hosted_checkout_url") or "")
        if not checkout_id or not page.startswith("https://"):
            _logger.error("sales.sumup.checkout_incomplete", fields=sorted(checkout))
            raise PaymentUnavailableError
        _logger.info("sales.sumup.checkout", order=request.order_number, checkout=checkout_id)
        return PaymentStart(provider=self.PROVIDER, provider_ref=checkout_id, checkout_url=page)

    async def outcome(self, provider_ref: str) -> PaymentOutcome:
        checkout = await self._call("GET", f"/v0.1/checkouts/{provider_ref}")
        status = checkout.get("status")
        if status == "PAID":
            transactions = checkout.get("transactions") or []
            successful = [t for t in transactions if t.get("status") == "SUCCESSFUL"]
            chosen = (successful or transactions or [{}])[0]
            return PaymentOutcome(
                progress=PaymentProgress.CAPTURED,
                transaction_ref=str(chosen.get("id")) if chosen.get("id") else None,
            )
        if status == "EXPIRED":
            return PaymentOutcome(progress=PaymentProgress.FAILED, failure_code="expired")
        return PaymentOutcome(progress=PaymentProgress.PENDING)

    async def abandon(self, provider_ref: str) -> None:
        # SumUp refuses to deactivate a checkout that was processed; _call raises then.
        await self._call("DELETE", f"/v0.1/checkouts/{provider_ref}")
        _logger.info("sales.sumup.checkout_closed", checkout=provider_ref)

    async def refund(self, *, refund_ref: str, amount_cents: int) -> None:
        # Always with the amount: all of it for a cancellation, a part after a partial return.
        await self._call(
            "POST",
            f"/v1.0/merchants/{self._merchant_code}/payments/{refund_ref}/refunds",
            json={"amount": _amount(amount_cents)},
        )
        _logger.info("sales.sumup.refund", transaction=refund_ref, amount_cents=amount_cents)

    async def _call(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        try:
            response = await self._client.request(method, path, **kwargs)
        except httpx.HTTPError as exc:
            _logger.warning("sales.sumup.unreachable", path=path, error=type(exc).__name__)
            raise PaymentUnavailableError from exc
        if response.status_code >= 400:  # noqa: PLR2004
            _logger.error(
                "sales.sumup.error",
                path=path,
                status=response.status_code,
                code=_error_code(response),
            )
            raise PaymentUnavailableError
        if not response.content:
            return {}
        data = response.json()
        return data if isinstance(data, dict) else {}


def _error_code(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return ""
    if isinstance(body, dict):
        return str(body.get("error_code") or body.get("code") or "")
    return ""


def build_payment_gateway(settings: Settings) -> PaymentGateway:
    """The configured provider."""
    match settings.payment_provider:
        case PaymentProvider.MOCK:
            return MockPaymentGateway()
        case PaymentProvider.SUMUP:
            return SumUpPaymentGateway(
                api_key=settings.sumup_api_key.get_secret_value(),
                merchant_code=settings.sumup_merchant_code,
                notify_url=f"{settings.public_base_url}/api/v1/webhooks/sumup",
                description=settings.shop_name,
                base_url=settings.sumup_api_url,
            )
        case PaymentProvider.OFF:
            return ClosedPaymentGateway()
