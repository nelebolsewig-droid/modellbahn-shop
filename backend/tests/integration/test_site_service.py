"""Fairs and the fair news against PostgreSQL, with the real outbox dispatcher."""

import re
from datetime import date, timedelta

import pytest
from sqlalchemy import func, update
from sqlalchemy.ext.asyncio import AsyncEngine

from modellbahn.modules.site.application.fairs import FairService
from modellbahn.modules.site.application.subscriptions import SubscriptionService
from modellbahn.modules.site.domain.dates import EN_DASH
from modellbahn.modules.site.domain.errors import (
    FairNotAnnounceableError,
    FairNotFoundError,
    SubscriptionTokenInvalidError,
)
from modellbahn.modules.site.domain.model import (
    CONFIRMATION_RESEND_INTERVAL,
    PENDING_RETENTION,
    Fair,
    FairDetails,
)
from modellbahn.platform.clock import FixedClock
from modellbahn.platform.mail import InMemoryMailer, OutgoingMail
from modellbahn.platform.outbox import outbox_table
from tests.conftest import Deliver
from tests.support import mails_to, token_from

pytestmark = pytest.mark.usefixtures("clean_database")

# The test clock stands on 22 October 2026.
ERIKA = "erika@example.de"


def fair_details(name: str, starts_on: date, days: int = 1) -> FairDetails:
    return FairDetails(
        name=name,
        venue="Kulturhaus",
        street="Hauptstraße 1",
        postal_code="06237",
        city="Leuna",
        booth="Stand 4",
        hours="Sa 10–17 Uhr",  # noqa: RUF001
        website_url="https://messe.example",
        note="",
        starts_on=starts_on,
        ends_on=starts_on + timedelta(days=days - 1),
    )


def unsubscribe_token(mail: OutgoingMail) -> str:
    match = re.search(r"/termine/abmelden\?token=([A-Za-z0-9_-]+)", mail.text)
    assert match is not None, "no way out in the mail"
    return match.group(1)


async def confirmed(
    fair_news: SubscriptionService, deliver: Deliver, mailer: InMemoryMailer, email: str
) -> None:
    await fair_news.subscribe(email)
    await deliver()
    await fair_news.confirm(token_from(mails_to(mailer, email)[-1]))


class TestFairs:
    async def test_the_shop_shows_published_fairs_to_come_and_the_last_ones(
        self, fairs: FairService
    ) -> None:
        await fairs.create(fair_details("Leuna", date(2026, 9, 12), days=2), published=True)
        await fairs.create(fair_details("Leipzig", date(2026, 10, 2), days=3), published=True)
        await fairs.create(fair_details("Entwurf", date(2026, 11, 1)), published=False)
        await fairs.create(fair_details("Dresden", date(2026, 11, 7)), published=True)
        # Runs over today: still "to come" until its last day is over.
        await fairs.create(fair_details("Heute", date(2026, 10, 21), days=3), published=True)

        shown = await fairs.calendar()
        assert [fair.name for fair in shown.upcoming] == ["Heute", "Dresden"]
        assert [fair.name for fair in shown.past] == ["Leipzig", "Leuna"]
        assert [fair.name for fair in await fairs.feed()] == [
            "Leuna",
            "Leipzig",
            "Heute",
            "Dresden",
        ]

    async def test_staff_change_and_remove_fairs(self, fairs: FairService) -> None:
        fair = await fairs.create(fair_details("Dresden", date(2026, 11, 7)), published=False)
        changed = await fairs.change(
            fair.id, fair_details("Kleinserienmesse Dresden", date(2026, 11, 7)), published=True
        )
        assert (changed.name, changed.published) == ("Kleinserienmesse Dresden", True)
        assert (await fairs.published(fair.id)).name == "Kleinserienmesse Dresden"
        await fairs.delete(fair.id)
        with pytest.raises(FairNotFoundError):
            await fairs.published(fair.id)
        assert await fairs.all() == []

    async def test_a_draft_is_not_in_the_shop(self, fairs: FairService) -> None:
        draft = await fairs.create(fair_details("Entwurf", date(2026, 11, 7)), published=False)
        with pytest.raises(FairNotFoundError):
            await fairs.published(draft.id)


class TestFairNews:
    async def test_double_opt_in(
        self, fair_news: SubscriptionService, deliver: Deliver, mailer: InMemoryMailer
    ) -> None:
        await fair_news.subscribe(ERIKA)
        assert await fair_news.counts() == {"pending": 1, "confirmed": 0}
        await deliver()
        [mail] = mails_to(mailer, ERIKA)
        assert mail.subject == "Bitte bestätige die Messe-Post von Modellbahn-Shop"
        assert "https://shop.test/termine/bestaetigen?token=" in mail.text
        assert "Glambecker Straße 2, 17235 Neustrelitz" in mail.text  # the sender's address

        with pytest.raises(SubscriptionTokenInvalidError):
            await fair_news.confirm("falsch")
        token = token_from(mail)
        await fair_news.confirm(token)
        assert await fair_news.counts() == {"pending": 0, "confirmed": 1}
        with pytest.raises(SubscriptionTokenInvalidError):
            await fair_news.confirm(token)  # used

    async def test_asking_again_does_not_flood_the_inbox(
        self,
        fair_news: SubscriptionService,
        deliver: Deliver,
        mailer: InMemoryMailer,
        clock: FixedClock,
    ) -> None:
        await fair_news.subscribe(ERIKA)
        await fair_news.subscribe("ERIKA@example.de")
        await deliver()
        assert len(mails_to(mailer, ERIKA)) == 1
        clock.advance(CONFIRMATION_RESEND_INTERVAL)
        await fair_news.subscribe(ERIKA)
        await deliver()
        first, second = mails_to(mailer, ERIKA)
        with pytest.raises(SubscriptionTokenInvalidError):
            await fair_news.confirm(token_from(first))  # replaced by the newer link
        await fair_news.confirm(token_from(second))
        await fair_news.subscribe(ERIKA)  # confirmed already: nothing to send
        await deliver()
        assert len(mails_to(mailer, ERIKA)) == 2

    async def test_unconfirmed_sign_ups_are_forgotten_after_a_week(
        self, fair_news: SubscriptionService, clock: FixedClock
    ) -> None:
        await fair_news.subscribe(ERIKA)
        assert await fair_news.purge_pending() == 0
        clock.advance(PENDING_RETENTION + timedelta(seconds=1))
        assert await fair_news.purge_pending() == 1
        assert await fair_news.counts() == {"pending": 0, "confirmed": 0}

    async def test_leaving_deletes_the_address(
        self,
        fairs: FairService,
        fair_news: SubscriptionService,
        deliver: Deliver,
        mailer: InMemoryMailer,
    ) -> None:
        await confirmed(fair_news, deliver, mailer, ERIKA)
        fair = await fairs.create(fair_details("Dresden", date(2026, 11, 7)), published=True)
        await fairs.announce(fair.id)
        await deliver()
        announcement = mails_to(mailer, ERIKA)[-1]
        assert "Keine Messe-Post mehr? Hier abmelden" in announcement.text
        await fair_news.unsubscribe(unsubscribe_token(announcement))
        assert await fair_news.counts() == {"pending": 0, "confirmed": 0}
        await fair_news.unsubscribe("schon-weg")  # an old link: nothing happens


class TestAnnouncement:
    async def test_goes_once_to_every_confirmed_subscriber(
        self,
        fairs: FairService,
        fair_news: SubscriptionService,
        deliver: Deliver,
        mailer: InMemoryMailer,
    ) -> None:
        await confirmed(fair_news, deliver, mailer, ERIKA)
        await confirmed(fair_news, deliver, mailer, "max@example.de")
        await fair_news.subscribe("noch-nicht@example.de")
        fair = await fairs.create(
            fair_details("8. Kühlungsborner Modellbahnausstellung", date(2026, 11, 20), days=3),
            published=True,
        )
        mailer.sent.clear()

        announcement = await fairs.announce(fair.id)
        assert announcement.recipients == 2
        await deliver()
        assert sorted(mail.to for mail in mailer.sent if "Wir stellen aus" in mail.subject) == [
            ERIKA,
            "max@example.de",
        ]
        mail = mails_to(mailer, ERIKA)[-1]
        when = f"20.{EN_DASH}22. November 2026"
        assert mail.subject == f"Wir stellen aus: 8. Kühlungsborner Modellbahnausstellung, {when}"
        assert "Stand 4" in mail.text
        assert f"https://shop.test/api/v1/store/fairs/{fair.id}/calendar.ics" in mail.text
        with pytest.raises(FairNotAnnounceableError, match="already_announced"):
            await fairs.announce(fair.id)

    async def test_a_retry_continues_where_it_stopped(
        self,
        fairs: FairService,
        fair_news: SubscriptionService,
        deliver: Deliver,
        mailer: InMemoryMailer,
        site_handlers: object,
        engine: AsyncEngine,
    ) -> None:
        await confirmed(fair_news, deliver, mailer, ERIKA)
        await confirmed(fair_news, deliver, mailer, "max@example.de")
        fair = await fairs.create(fair_details("Dresden", date(2026, 11, 7)), published=True)
        await fairs.announce(fair.id)

        failing = FailAfter(mailer, successes=1)
        handlers = site_handlers
        handlers._mailer = failing  # type: ignore[attr-defined]
        await deliver()  # the first mail goes out, the second fails
        handlers._mailer = mailer  # type: ignore[attr-defined]
        async with engine.begin() as connection:  # the retry is due at once
            await connection.execute(update(outbox_table).values(next_attempt_at=func.now()))
        await deliver()  # the retry sends only the missing one
        announced = [mail.to for mail in mailer.sent if mail.subject.startswith("Wir stellen")]
        assert sorted(announced) == [ERIKA, "max@example.de"]

    async def test_only_published_fairs_still_to_come(
        self, fairs: FairService, clock: FixedClock
    ) -> None:
        draft = await fairs.create(fair_details("Entwurf", date(2026, 11, 7)), published=False)
        with pytest.raises(FairNotAnnounceableError, match="not_published"):
            await fairs.announce(draft.id)
        past: Fair = await fairs.create(fair_details("Leipzig", date(2026, 10, 2)), published=True)
        with pytest.raises(FairNotAnnounceableError, match="past"):
            await fairs.announce(past.id)
        assert clock.now().date() == date(2026, 10, 22)


class FailAfter(InMemoryMailer):
    """Delivers ``successes`` mails into ``target``, then refuses (an SMTP outage)."""

    def __init__(self, target: InMemoryMailer, *, successes: int) -> None:
        super().__init__()
        self._target = target
        self._left = successes

    async def send(self, mail: OutgoingMail) -> None:
        if self._left == 0:
            msg = "SMTP down"
            raise ConnectionError(msg)
        self._left -= 1
        await self._target.send(mail)
