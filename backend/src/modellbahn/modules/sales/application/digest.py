"""The morning mail „Heute dran“ (ADR 0034): once a day, to the shop's own address, what
waits to be packed, made and printed, and what came in yesterday.

The worker asks every few minutes; from 7 o'clock shop time the first ask of the day
claims the day and sends. A mail that fails rolls the claim back, the next ask tries again.
"""

from datetime import time
from typing import Final

import structlog

from modellbahn.modules.sales.application import mails
from modellbahn.modules.sales.application.common import UnitOfWorkFactory
from modellbahn.platform.clock import Clock
from modellbahn.platform.mail import Mailer, compose

_logger = structlog.get_logger(__name__)

SEND_FROM: Final = time(7, 0)
SEND_UNTIL: Final = time(18, 0)
"""A worker down all day does not send yesterday's news in the evening."""


class MorningDigest:
    def __init__(
        self,
        *,
        uow_factory: UnitOfWorkFactory,
        clock: Clock,
        mailer: Mailer,
        shop_email: str,
        public_base_url: str,
        shop_name: str,
        sender: tuple[str, ...] = (),
    ) -> None:
        self._uow = uow_factory
        self._clock = clock
        self._mailer = mailer
        self._shop_email = shop_email
        self._base_url = public_base_url
        self._shop_name = shop_name
        self._sender = sender

    async def send_if_due(self) -> bool:
        """Send today's mail if it is time and nobody has; True if this call sent it."""
        if not self._shop_email:
            return False
        now = self._clock.now()
        local = now.astimezone(mails.SHOP_TIME_ZONE)
        if not SEND_FROM <= local.time() < SEND_UNTIL:
            return False
        async with self._uow() as uow:
            if not await uow.digests.claim(local.date(), now):
                return False
            facts = await uow.digests.facts(now)
            content = mails.morning_mail(facts, day=local.date(), base_url=self._base_url)
            await self._mailer.send(
                compose(
                    content, to=self._shop_email, shop_name=self._shop_name, sender=self._sender
                )
            )
            await uow.commit()
        _logger.info("sales.digest.sent", day=local.date().isoformat(), to_pack=facts.to_pack)
        return True
