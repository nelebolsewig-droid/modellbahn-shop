"""The newsletter's rules without a database: issue days and what suits whom."""

from datetime import UTC, date, datetime, timedelta
from uuid import uuid4

from modellbahn.modules.newsletter.domain.model import (
    Bought,
    Model,
    is_issue_day,
    new_models,
    next_issue_day,
    suggest,
)
from modellbahn.platform.mail import MailCard, MailContent, MailSection, compose

NOW = datetime(2026, 12, 1, 9, 0, tzinfo=UTC)
LKW, PKW, STRASSE = uuid4(), uuid4(), uuid4()


def model(
    slug: str, *categories: object, scales: tuple[str, ...] = ("H0",), age: int = 60
) -> Model:
    return Model(
        product_id=uuid4(),
        slug=slug,
        published_at=NOW - timedelta(days=age),
        category_ids=tuple(categories),  # type: ignore[arg-type]
        scale_codes=scales,
    )


class TestIssueDays:
    def test_the_1st_and_the_15th(self) -> None:
        assert is_issue_day(date(2026, 12, 1), (1, 15))
        assert is_issue_day(date(2026, 12, 15), (1, 15))
        assert not is_issue_day(date(2026, 12, 2), (1, 15))

    def test_the_31st_falls_on_the_last_day_of_a_short_month(self) -> None:
        assert is_issue_day(date(2027, 2, 28), (31,))
        assert not is_issue_day(date(2027, 3, 30), (31,))

    def test_the_next_one(self) -> None:
        assert next_issue_day(date(2026, 12, 2), (1, 15)) == date(2026, 12, 15)
        assert next_issue_day(date(2026, 12, 16), (1, 15)) == date(2027, 1, 1)
        assert next_issue_day(date(2026, 12, 16), ()) is None


class TestWhatIsNew:
    def test_only_after_the_last_issue_and_the_newest_first(self) -> None:
        old, newer, newest = model("alt", age=40), model("b", age=5), model("c", age=1)
        assert new_models([old, newer, newest], NOW - timedelta(days=30)) == [newest, newer]


class TestSuggestions:
    def test_same_category_and_scale_first_never_what_they_own(self) -> None:
        w50 = model("w50", LKW, STRASSE)
        l60 = model("l60", LKW, STRASSE)
        trabant = model("trabant", PKW, STRASSE)
        tt_lkw = model("lkw-tt", LKW, STRASSE, scales=("TT",))
        found = suggest([w50, l60, trabant, tt_lkw], [Bought("w50", "H0")], shown=set())
        assert found == [l60, trabant]

    def test_nothing_bought_nothing_suggested_and_nothing_twice(self) -> None:
        w50, l60 = model("w50", LKW), model("l60", LKW)
        assert suggest([w50, l60], [], shown=set()) == []
        assert suggest([w50, l60], [Bought("w50", "H0")], shown={l60.product_id}) == []


class TestMailCards:
    def test_cards_in_text_and_html_with_the_way_out(self) -> None:
        content = MailContent(
            subject="Neu",
            greeting="Hallo,",
            paragraphs=("Text",),
            sections=(
                MailSection(
                    heading="Neu in der Werkstatt",
                    cards=(
                        MailCard(
                            title="IFA W50 <LKW>",
                            url="https://shop.test/produkte/w50",
                            price="ab 49,90 €",
                            image_url="https://shop.test/medien/w50.webp",
                        ),
                    ),
                ),
            ),
        )
        mail = compose(content, to="a@b.de", shop_name="adp-Modelle", unsubscribe_url="https://x/y")
        assert "* IFA W50 <LKW> (ab 49,90 €)" in mail.text
        assert "IFA W50 &lt;LKW&gt;" in mail.html
        assert 'src="https://shop.test/medien/w50.webp"' in mail.html
        assert mail.unsubscribe_url == "https://x/y"
