"""Use cases around the fairs: staff keep the dates, the shop shows them."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Final
from uuid import UUID
from zoneinfo import ZoneInfo

from modellbahn.modules.site.application.ports import SiteUnitOfWork, UnitOfWorkFactory
from modellbahn.modules.site.domain.errors import FairNotFoundError
from modellbahn.modules.site.domain.model import Fair, FairDetails, SubscriptionStatus
from modellbahn.platform.clock import Clock

SHOP_TIME_ZONE: Final = ZoneInfo("Europe/Berlin")
# The shop looks back on the last few fairs ("Rückblick").
PAST_FAIRS_SHOWN: Final = 4
# The calendar feed keeps a year of past fairs, so subscribed calendars do not lose them.
CALENDAR_LOOKBACK: Final = timedelta(days=365)


def today(clock: Clock) -> date:
    """The current day where the shop is: a fair "ends today" until midnight in Germany."""
    return clock.now().astimezone(SHOP_TIME_ZONE).date()


@dataclass(frozen=True, slots=True)
class FairCalendar:
    """The fairs as the shop shows them: what is to come, and the last ones."""

    upcoming: Sequence[Fair]
    past: Sequence[Fair]


@dataclass(frozen=True, slots=True)
class Announcement:
    fair: Fair
    recipients: int


class FairService:
    def __init__(self, *, uow_factory: UnitOfWorkFactory, clock: Clock) -> None:
        self._uow = uow_factory
        self._clock = clock

    # --- Shop -------------------------------------------------------------------------

    async def calendar(self) -> FairCalendar:
        day = today(self._clock)
        async with self._uow() as uow:
            upcoming = await uow.fairs.published_from(day)
            past = await uow.fairs.published_before(day, PAST_FAIRS_SHOWN)
        return FairCalendar(upcoming=upcoming, past=past)

    async def feed(self) -> Sequence[Fair]:
        """What a subscribed calendar gets: the coming fairs and those of the last year."""
        async with self._uow() as uow:
            return await uow.fairs.published_from(today(self._clock) - CALENDAR_LOOKBACK)

    async def published(self, fair_id: UUID) -> Fair:
        async with self._uow() as uow:
            fair = await uow.fairs.get(fair_id)
        if fair is None or not fair.published:
            raise FairNotFoundError
        return fair

    # --- Stellwerk --------------------------------------------------------------------

    async def all(self) -> Sequence[Fair]:
        async with self._uow() as uow:
            return await uow.fairs.all()

    async def create(self, details: FairDetails, *, published: bool) -> Fair:
        async with self._uow() as uow:
            fair = Fair.create(details, published=published, now=self._clock.now())
            uow.fairs.add(fair)
            await uow.commit()
        return fair

    async def change(self, fair_id: UUID, details: FairDetails, *, published: bool) -> Fair:
        async with self._uow() as uow:
            fair = await self._locked(uow, fair_id)
            fair.change(details, published=published, now=self._clock.now())
            await uow.commit()
        return fair

    async def delete(self, fair_id: UUID) -> None:
        async with self._uow() as uow:
            fair = await self._locked(uow, fair_id)
            await uow.fairs.delete(fair)
            await uow.commit()

    async def announce(self, fair_id: UUID) -> Announcement:
        """Mail the fair to every confirmed subscriber (the worker sends the mails)."""
        async with self._uow() as uow:
            fair = await self._locked(uow, fair_id)
            uow.publish(fair.announce(today=today(self._clock), now=self._clock.now()))
            recipients = (await uow.subscriptions.counts())[SubscriptionStatus.CONFIRMED.value]
            await uow.commit()
        return Announcement(fair=fair, recipients=recipients)

    @staticmethod
    async def _locked(uow: SiteUnitOfWork, fair_id: UUID) -> Fair:
        fair = await uow.fairs.get(fair_id, for_update=True)
        if fair is None:
            raise FairNotFoundError
        return fair
