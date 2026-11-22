"""Visitors of the shop per day, counted without cookies and without keeping who (ADR 0043).

Each page view of the shop sends a beacon. A visitor is the address and browser of a
request, hashed with a salt that exists for one day only: the same visitor counts once a
day, and after midnight neither the salt nor the hashes are left, so nobody can be
recognised again, not even from one day to the next. What stays is two numbers per day.
"""

import hashlib
import re
import secrets
from collections.abc import Sequence
from datetime import timedelta
from typing import Final

from modellbahn.modules.site.application.fairs import today
from modellbahn.modules.site.application.ports import UnitOfWorkFactory
from modellbahn.modules.site.domain.model import VisitDay
from modellbahn.platform.clock import Clock

SALT_BYTES: Final = 16
DAYS_MAX: Final = 366
# Crawlers, link previews and test browsers are no visitors. Most of them run no script
# and never send the beacon; these say what they are in their user agent.
_ROBOT: Final = re.compile(
    r"bot|crawl|spider|slurp|preview|headless|lighthouse|pingdom|monitor|curl|wget|python"
    r"|facebookexternalhit|embedly|whatsapp|telegram",
    re.IGNORECASE,
)


def is_robot(user_agent: str) -> bool:
    return not user_agent.strip() or _ROBOT.search(user_agent) is not None


def visitor_mark(salt: bytes, address: str, user_agent: str) -> str:
    """The visitor of a day as a hash; without that day's salt it says nothing."""
    digest = hashlib.blake2b(f"{address}\n{user_agent}".encode(), key=salt, digest_size=16)
    return digest.hexdigest()


class VisitService:
    def __init__(self, *, uow_factory: UnitOfWorkFactory, clock: Clock) -> None:
        self._uow = uow_factory
        self._clock = clock

    async def record(self, *, address: str, user_agent: str) -> None:
        """Count a page view, and its visitor if they are new today."""
        if is_robot(user_agent):
            return
        day = today(self._clock)
        async with self._uow() as uow:
            salt, new_day = await uow.visits.salt(day, secrets.token_bytes(SALT_BYTES))
            if new_day:
                await uow.visits.forget_before(day)
            new_visitor = await uow.visits.mark(day, visitor_mark(salt, address, user_agent))
            await uow.visits.count(day, new_visitor=new_visitor)
            await uow.commit()

    async def last_days(self, days: int) -> Sequence[VisitDay]:
        """The last ``days`` days up to today, the oldest first; days without visits as 0."""
        last = today(self._clock)
        first = last - timedelta(days=days - 1)
        async with self._uow() as uow:
            counted = {row.day: row for row in await uow.visits.between(first, last)}
        return [
            counted.get(
                first + timedelta(days=offset), VisitDay(first + timedelta(days=offset), 0, 0)
            )
            for offset in range(days)
        ]
