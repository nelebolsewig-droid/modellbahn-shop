"""The site's model without a database: fairs, German dates, double opt-in, calendar."""

from datetime import UTC, date, datetime, timedelta
from uuid import UUID

import pytest

from modellbahn.modules.site.application.ical import calendar
from modellbahn.modules.site.domain.dates import EN_DASH, date_range, long_date
from modellbahn.modules.site.domain.errors import (
    FairNotAnnounceableError,
    InvalidFieldError,
    SubscriptionTokenInvalidError,
)
from modellbahn.modules.site.domain.events import FairAnnounced
from modellbahn.modules.site.domain.model import (
    CONFIRMATION_LIFETIME,
    CONFIRMATION_RESEND_INTERVAL,
    Fair,
    FairDetails,
    Subscription,
    normalize_email,
)
from modellbahn.platform.imprint import Imprint

NOW = datetime(2026, 10, 28, 9, 0, tzinfo=UTC)
TODAY = date(2026, 10, 28)


def details(**changes: object) -> FairDetails:
    values: dict[str, object] = {
        "name": " Kleinserienmesse   Dresden ",
        "venue": "JohannStadthalle",
        "street": "Holbeinstraße 68",
        "postal_code": "01307",
        "city": "Dresden",
        "booth": "",
        "hours": " Sa 10–17 Uhr \n\n",  # noqa: RUF001
        "website_url": "",
        "note": "",
        "starts_on": date(2026, 11, 7),
        "ends_on": date(2026, 11, 7),
        **changes,
    }
    return FairDetails(**values)  # type: ignore[arg-type]


class TestDates:
    @pytest.mark.parametrize(
        ("start", "end", "text"),
        [
            (date(2026, 11, 7), date(2026, 11, 7), "7. November 2026"),
            (date(2026, 11, 20), date(2026, 11, 22), f"20.{EN_DASH}22. November 2026"),
            (date(2026, 10, 30), date(2026, 11, 1), f"30. Oktober {EN_DASH} 1. November 2026"),
            (date(2026, 12, 30), date(2027, 1, 2), f"30. Dezember 2026 {EN_DASH} 2. Januar 2027"),
        ],
    )
    def test_ranges_name_month_and_year_once(self, start: date, end: date, text: str) -> None:
        assert date_range(start, end) == text

    def test_march_has_its_umlaut(self) -> None:
        assert long_date(date(2027, 3, 6)) == "6. März 2027"


class TestFair:
    def test_details_are_tidied(self) -> None:
        fair = Fair.create(details(), published=True, now=NOW)
        assert fair.name == "Kleinserienmesse Dresden"
        assert fair.hours == "Sa 10–17 Uhr"  # noqa: RUF001
        assert fair.place() == "JohannStadthalle, Holbeinstraße 68, 01307 Dresden"

    @pytest.mark.parametrize(
        ("changes", "field"),
        [
            ({"ends_on": date(2026, 11, 6)}, "ends_on"),
            ({"ends_on": date(2026, 11, 21)}, "ends_on"),
            ({"name": "  "}, "name"),
            ({"city": ""}, "city"),
            ({"website_url": "javascript:alert(1)"}, "website_url"),
        ],
    )
    def test_refuses_what_cannot_be_right(self, changes: dict[str, object], field: str) -> None:
        with pytest.raises(InvalidFieldError) as error:
            Fair.create(details(**changes), published=False, now=NOW)
        assert error.value.field == field

    def test_is_announced_once_while_published_and_ahead(self) -> None:
        draft = Fair.create(details(), published=False, now=NOW)
        with pytest.raises(FairNotAnnounceableError, match="not_published"):
            draft.announce(today=TODAY, now=NOW)
        fair = Fair.create(details(), published=True, now=NOW)
        event = fair.announce(today=TODAY, now=NOW)
        assert isinstance(event, FairAnnounced)
        assert event.public_payload() == {"fair_id": str(fair.id), "name": fair.name}
        with pytest.raises(FairNotAnnounceableError, match="already_announced"):
            fair.announce(today=TODAY, now=NOW)
        over = Fair.create(details(), published=True, now=NOW)
        with pytest.raises(FairNotAnnounceableError, match="past"):
            over.announce(today=date(2026, 11, 8), now=NOW)


class TestSubscription:
    def test_asks_once_and_again_only_after_a_while(self) -> None:
        subscription, event = Subscription.request(
            email=" Erika@Example.DE ", unsubscribe_token="leave", now=NOW
        )
        assert subscription.email == "Erika@example.de"
        assert event.aggregate_id == subscription.id
        assert subscription.request_again(NOW + timedelta(minutes=1)) is None
        assert subscription.request_again(NOW + CONFIRMATION_RESEND_INTERVAL) is not None

    def test_confirms_within_the_lifetime_of_the_link(self) -> None:
        subscription, _ = Subscription.request(email="a@b.de", unsubscribe_token="x", now=NOW)
        with pytest.raises(SubscriptionTokenInvalidError):
            subscription.confirm(NOW)  # no link issued yet
        subscription.issue_confirmation("hash", NOW)
        late = NOW + CONFIRMATION_LIFETIME
        with pytest.raises(SubscriptionTokenInvalidError):
            subscription.confirm(late)
        subscription.confirm(late - timedelta(seconds=1))
        assert subscription.is_confirmed
        assert subscription.confirm_token_hash is None
        assert subscription.request_again(late + CONFIRMATION_RESEND_INTERVAL) is None

    @pytest.mark.parametrize("address", ["", "kein-at", "a@b", "a @b.de", "x" * 250 + "@b.de"])
    def test_refuses_what_is_no_address(self, address: str) -> None:
        with pytest.raises(InvalidFieldError):
            normalize_email(address)


class TestCalendar:
    def test_all_day_events_with_escaped_text_and_folded_lines(self) -> None:
        fair = Fair.create(
            details(
                name="8. Kühlungsborner Modellbahnausstellung, mit Sonderschau",
                starts_on=date(2026, 11, 20),
                ends_on=date(2026, 11, 22),
                note="Eintritt frei; Kinder willkommen. " * 4,
            ),
            published=True,
            now=NOW,
        )
        fair.id = UUID("01a181f5-c7a4-76e1-8ffb-af1e1096ab74")
        text = calendar([fair], shop_name="adp-Modelle", base_url="https://shop.test")
        assert text.startswith("BEGIN:VCALENDAR\r\nVERSION:2.0\r\n")
        assert text.endswith("END:VCALENDAR\r\n")
        assert "DTSTART;VALUE=DATE:20261120\r\n" in text
        assert "DTEND;VALUE=DATE:20261123\r\n" in text  # exclusive: the day after
        assert "UID:fair-01a181f5-c7a4-76e1-8ffb-af1e1096ab74@shop.test" in text
        unfolded = text.replace("\r\n ", "")
        assert r"Modellbahnausstellung\, mit Sonderschau" in unfolded
        assert r"Eintritt frei\; Kinder willkommen." in unfolded
        assert all(len(line.encode()) <= 75 for line in text.split("\r\n"))


class TestImprint:
    def test_closes_mails_with_who_where_and_how_to_reach(self) -> None:
        imprint = Imprint(
            shop_name="adp-Modelle",
            company="adp-Modelle",
            owner="Johann-Leon Diesterhaupt",
            street="Glambecker Straße 2",
            postal_code="17235",
            city="Neustrelitz",
            country="Deutschland",
            phone="",
            email="info@adp-modelle.de",
            vat_id="",
        )
        assert imprint.is_complete
        assert imprint.mail_footer() == (
            "adp-Modelle · Johann-Leon Diesterhaupt",
            "Glambecker Straße 2, 17235 Neustrelitz",
            "info@adp-modelle.de",
        )
