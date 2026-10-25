"""Payment providers behind the ``PaymentGateway`` port. For now only the mock.

A real provider (e.g. Stripe) becomes another adapter here; its model of payments,
customers and errors stays in this file and never reaches the domain (KONZEPT §2.6).
"""

from enum import StrEnum
from typing import Final

import structlog

from modellbahn.modules.sales.domain.errors import InvalidFieldError, PaymentUnavailableError
from modellbahn.modules.sales.domain.model import ChargeResult
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

    async def charge(self, *, order_number: str, amount_cents: int, method: str) -> ChargeResult:
        try:
            scenario = MockScenario(method)
        except ValueError:
            raise InvalidFieldError("method", "unknown", "not a payment method") from None
        _logger.info(
            "sales.mock_payment", order=order_number, amount_cents=amount_cents, scenario=scenario
        )
        reference = f"mock_{new_id().hex}"
        match scenario:
            case MockScenario.SUCCEEDS:
                return ChargeResult(captured=True, provider=self.PROVIDER, provider_ref=reference)
            case MockScenario.DECLINED:
                return ChargeResult(
                    captured=False,
                    provider=self.PROVIDER,
                    provider_ref=reference,
                    failure_code="declined",
                )
            case MockScenario.FAILS:
                raise PaymentUnavailableError

    async def refund(self, *, provider_ref: str, amount_cents: int) -> None:
        _logger.info("sales.mock_refund", provider_ref=provider_ref, amount_cents=amount_cents)
