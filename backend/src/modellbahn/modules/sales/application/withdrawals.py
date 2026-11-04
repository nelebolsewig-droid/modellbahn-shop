"""The withdrawal function (§ 356a BGB, ADR 0020): take a declaration, show it to staff.

A consumer withdraws by giving their name, the order number and an e-mail address for the
confirmation, then confirming. The declaration is stored with the time it came in; the
worker sends the confirmation of receipt and tells the shop (``handlers``).
"""

from uuid import UUID

import structlog

from modellbahn.modules.sales.application.common import UnitOfWorkFactory
from modellbahn.modules.sales.domain.withdrawals import ORDER_REFERENCE_MAX_LENGTH, Withdrawal
from modellbahn.platform.clock import Clock

_logger = structlog.get_logger(__name__)

RECENT_LIMIT_MAX = 200


class WithdrawalService:
    def __init__(self, *, uow_factory: UnitOfWorkFactory, clock: Clock) -> None:
        self._uow = uow_factory
        self._clock = clock

    async def declare(self, *, name: str, order_number: str, email: str, scope: str) -> Withdrawal:
        """Take a declaration of withdrawal; it counts from the moment it is stored."""
        async with self._uow() as uow:
            reference = order_number.strip().upper()
            order = (
                await uow.orders.get_by_number(reference)
                if 0 < len(reference) <= ORDER_REFERENCE_MAX_LENGTH
                else None
            )
            withdrawal, received = Withdrawal.declare(
                name=name,
                order_reference=order_number,
                email=email,
                scope=scope,
                order=order,
                now=self._clock.now(),
            )
            uow.withdrawals.add(withdrawal)
            uow.publish(received)
            await uow.commit()
        _logger.info(
            "sales.withdrawal.received",
            withdrawal_id=str(withdrawal.id),
            order=received.number,
            matched=withdrawal.order_id is not None,
        )
        return withdrawal

    async def recent(self, *, limit: int, order_id: UUID | None = None) -> list[Withdrawal]:
        """The latest declarations, for the admin area; those of one order if it is given."""
        async with self._uow() as uow:
            return await uow.withdrawals.recent(
                limit=min(limit, RECENT_LIMIT_MAX), order_id=order_id
            )
