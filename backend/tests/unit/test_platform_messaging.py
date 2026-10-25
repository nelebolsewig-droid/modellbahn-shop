"""Mail rendering and sending, outbox back-off, realtime notifications and subscriptions."""

from datetime import timedelta
from email.message import EmailMessage
from uuid import uuid4

import pytest

from modellbahn.platform.config import Settings
from modellbahn.platform.mail import MailAction, MailContent, SmtpMailer, compose
from modellbahn.platform.outbox import (
    MAX_NOTIFICATION_BYTES,
    HandlerRegistry,
    RealtimeEvent,
    retry_delay,
)
from modellbahn.platform.realtime import Subscription, to_server_sent_event
from tests.support import NOW, SampleHappened, sample


def content() -> MailContent:
    return MailContent(
        subject="Betreff",
        greeting="Hallo <Erika>,",
        paragraphs=("Erster Absatz.", "Zweiter & letzter Absatz."),
        action=MailAction(label="Los geht's", url="https://shop.test/x?token=a&b=c"),
        closing=("Gruß",),
    )


class TestMail:
    def test_compose_renders_text_and_escaped_html(self) -> None:
        rendered = compose(content(), to="kunde@example.com", shop_name="Gleiswerk")
        assert rendered.to == "kunde@example.com"
        assert rendered.subject == "Betreff"
        assert "Hallo <Erika>,\n\nErster Absatz." in rendered.text
        assert "Los geht's:\nhttps://shop.test/x?token=a&b=c" in rendered.text
        assert rendered.text.endswith("Antworten darauf erreichen niemanden.\n")
        assert "Viele Grüße\nGleiswerk" in rendered.text
        assert "Hallo &lt;Erika&gt;," in rendered.html
        assert 'href="https://shop.test/x?token=a&amp;b=c"' in rendered.html
        assert '<html lang="de">' in rendered.html

    def test_compose_without_action(self) -> None:
        rendered = compose(
            MailContent(subject="S", greeting="Hallo,", paragraphs=("Text.",)),
            to="a@example.com",
            shop_name="Shop",
        )
        assert "href" not in rendered.html

    async def test_smtp_mailer_builds_a_multipart_message(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        sent: list[tuple[EmailMessage, dict[str, object]]] = []

        async def fake_send(message: EmailMessage, **options: object) -> None:
            sent.append((message, options))

        monkeypatch.setattr("aiosmtplib.send", fake_send)
        settings = Settings(
            smtp_host="smtp.example",
            smtp_port=587,
            smtp_starttls=True,
            smtp_username="shop",
            smtp_password="geheim",  # type: ignore[arg-type]  # pydantic coerces to SecretStr
            smtp_from="Gleiswerk <shop@gleiswerk.example>",
        )
        await SmtpMailer(settings).send(compose(content(), to="a@example.com", shop_name="G"))

        ((message, options),) = sent
        assert message["From"] == "Gleiswerk <shop@gleiswerk.example>"
        assert message["To"] == "a@example.com"
        assert message["Message-ID"].endswith("@gleiswerk.example>")
        assert [part.get_content_type() for part in message.iter_parts()] == [
            "text/plain",
            "text/html",
        ]
        assert options["hostname"] == "smtp.example"
        assert options["port"] == 587
        assert options["start_tls"] is True
        assert options["username"] == "shop"
        assert options["password"] == "geheim"


class TestOutboxBackoff:
    @pytest.mark.parametrize(
        ("attempts", "delay"),
        [
            (1, timedelta(seconds=30)),
            (2, timedelta(seconds=60)),
            (3, timedelta(seconds=120)),
            (7, timedelta(seconds=1920)),
            (8, timedelta(hours=1)),
            (100, timedelta(hours=1)),
        ],
    )
    def test_doubles_and_caps_at_one_hour(self, attempts: int, delay: timedelta) -> None:
        assert retry_delay(attempts) == delay


class TestHandlerRegistry:
    async def test_handlers_receive_their_event_type_only(self) -> None:
        registry = HandlerRegistry()
        received: list[SampleHappened] = []

        async def handler(event: SampleHappened) -> None:
            received.append(event)

        registry.register(SampleHappened, handler)
        (typed,) = registry.handlers_for(SampleHappened.event_type)
        assert typed.name.endswith("handler")
        event = sample()
        await typed.handle(event)
        assert received == [event]
        assert registry.handlers_for("test.other") == []

    def test_several_modules_may_react_to_one_event_type(self) -> None:
        registry = HandlerRegistry()

        async def send_mail(event: SampleHappened) -> None: ...

        async def allocate(event: SampleHappened) -> None: ...

        registry.register(SampleHappened, send_mail)
        registry.register(SampleHappened, allocate, name="inventory.allocate")

        names = [entry.name for entry in registry.handlers_for(SampleHappened.event_type)]
        assert names[0].endswith("send_mail")
        assert names[1] == "inventory.allocate"

    def test_a_name_is_used_once_per_event_type(self) -> None:
        # The delivery state is kept by name; two handlers under one name would share it.
        registry = HandlerRegistry()

        async def first(event: SampleHappened) -> None: ...

        async def second(event: SampleHappened) -> None: ...

        registry.register(SampleHappened, first, name="same")

        with pytest.raises(ValueError, match="already has a handler named 'same'"):
            registry.register(SampleHappened, second, name="same")


class TestRealtimeNotification:
    def test_round_trip(self) -> None:
        event = RealtimeEvent.from_domain_event(sample())
        assert event.audience == frozenset({"staff"})
        assert RealtimeEvent.from_notification(event.to_notification()) == event

    def test_oversized_data_is_dropped_and_flagged(self) -> None:
        event = RealtimeEvent(
            id=uuid4(),
            type="test.big",
            audience=frozenset({"staff"}),
            occurred_at=NOW,
            data={"blob": "x" * MAX_NOTIFICATION_BYTES},
        )
        notification = event.to_notification()
        assert len(notification.encode()) < MAX_NOTIFICATION_BYTES
        restored = RealtimeEvent.from_notification(notification)
        assert restored.truncated
        assert restored.data == {}

    def test_server_sent_event_frame(self) -> None:
        event = RealtimeEvent.from_domain_event(sample())
        frame = to_server_sent_event(event)
        assert frame.id == str(event.id)
        assert frame.event == "test.sample.happened"
        assert frame.raw_data is not None
        assert f'"id":"{event.id}"' in frame.raw_data


def realtime_event(audience: str = "staff") -> RealtimeEvent:
    return RealtimeEvent(
        id=uuid4(), type="test.x", audience=frozenset({audience}), occurred_at=NOW, data={}
    )


class TestSubscription:
    def test_filters_by_audience(self) -> None:
        subscription = Subscription(audience="staff")
        subscription.offer(realtime_event("customers"))
        assert subscription.queue.empty()

    async def test_slow_client_loses_the_oldest_events(self) -> None:
        subscription = Subscription(audience="staff")
        events = [realtime_event() for _ in range(subscription.queue.maxsize + 2)]
        for event in events:
            subscription.offer(event)
        assert subscription.dropped == 2
        subscription.close()
        received = [event async for event in subscription]
        # The closing marker displaced one more event to make room.
        assert received == events[3:]
