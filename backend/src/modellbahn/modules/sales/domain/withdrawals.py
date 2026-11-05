"""Withdrawals declared with the shop's withdrawal function (§ 356a BGB, ADR 0020).

The function takes every declaration, as a letter would be taken: whether it is valid (in
time, by a consumer, about an order of ours) is for staff to judge. What it records is
what the consumer declared and when it came in, which the confirmation repeats.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Final
from uuid import UUID

from modellbahn.modules.sales.domain.errors import InvalidFieldError
from modellbahn.modules.sales.domain.events import WithdrawalReceived
from modellbahn.modules.sales.domain.model import Order, normalize_email
from modellbahn.platform.ids import new_id

WITHDRAWAL_NAME_MAX_LENGTH: Final = 200
ORDER_REFERENCE_MAX_LENGTH: Final = 40
WITHDRAWAL_SCOPE_MAX_LENGTH: Final = 1000


def _clean(value: str, field_name: str, max_length: int, *, required: bool) -> str:
    cleaned = " ".join(value.split())
    if required and not cleaned:
        raise InvalidFieldError(field_name, "required", "must not be empty")
    if len(cleaned) > max_length:
        raise InvalidFieldError(field_name, "too_long", f"at most {max_length} characters")
    return cleaned


@dataclass(eq=False)
class Withdrawal:
    """A declaration of withdrawal as it came in. Never changed afterwards."""

    id: UUID
    received_at: datetime
    name: str
    order_reference: str
    """The order number as the consumer gave it (trimmed, upper-cased)."""
    email: str
    """Where the confirmation of receipt goes."""
    scope: str
    """What is withdrawn, in the consumer's words; empty for the whole order."""
    order_id: UUID | None
    """The order it names, when number and e-mail address fit one of ours."""

    @classmethod
    def declare(
        cls,
        *,
        name: str,
        order_reference: str,
        email: str,
        scope: str,
        order: Order | None,
        now: datetime,
    ) -> tuple["Withdrawal", WithdrawalReceived]:
        """Take a declaration; ``order`` is the order with the given number, if there is one.

        The declaration names that order only if its e-mail address fits too, so that a
        number alone tells nobody whether an order exists.
        """
        reference = _clean(
            order_reference, "order_number", ORDER_REFERENCE_MAX_LENGTH, required=True
        ).upper()
        address = normalize_email(email)
        named = (
            order
            if order is not None
            and order.number == reference
            and order.email.casefold() == address.casefold()
            else None
        )
        withdrawal = cls(
            id=new_id(),
            received_at=now,
            name=_clean(name, "name", WITHDRAWAL_NAME_MAX_LENGTH, required=True),
            order_reference=reference,
            email=address,
            scope=_clean(scope, "scope", WITHDRAWAL_SCOPE_MAX_LENGTH, required=False),
            order_id=named.id if named is not None else None,
        )
        event = WithdrawalReceived(
            aggregate_id=withdrawal.id,
            occurred_at=now,
            order_id=withdrawal.order_id,
            number=named.number if named is not None else None,
        )
        return withdrawal, event

    @property
    def whole_order(self) -> bool:
        return not self.scope
