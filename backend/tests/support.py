"""Helpers shared by the test packages."""

import asyncio
import contextlib
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from types import TracebackType
from typing import ClassVar, Final, Self
from uuid import UUID, uuid4

import asyncpg
from alembic import command
from alembic.config import Config
from sqlalchemy.engine import make_url
from starlette.types import ASGIApp, Message

from modellbahn.platform.db import asyncpg_dsn
from modellbahn.platform.events import DomainEvent
from modellbahn.platform.mail import InMemoryMailer, OutgoingMail

NOW: Final = datetime(2026, 10, 22, 10, 0, tzinfo=UTC)
BACKEND_ROOT: Final = Path(__file__).resolve().parents[1]
CSRF_HEADERS: Final = {"X-Modellbahn-Client": "web"}
_TOKEN_IN_LINK: Final = re.compile(r"[?&]token=([A-Za-z0-9_-]+)")


# --- A test event, deliberately not in the global registry ------------------------------


class Colour(StrEnum):
    RED = "red"


@dataclass(frozen=True, kw_only=True)
class SampleHappened(DomainEvent):
    event_type: ClassVar[str] = "test.sample.happened"
    aggregate_type: ClassVar[str] = "test.sample"
    audience: ClassVar[frozenset[str]] = frozenset({"staff"})

    name: str
    count: int
    ratio: float
    flag: bool
    other: UUID
    when: datetime
    colour: Colour
    note: str | None = None


def sample() -> SampleHappened:
    return SampleHappened(
        aggregate_id=uuid4(),
        occurred_at=NOW,
        name="Stellwerk",
        count=3,
        ratio=0.5,
        flag=True,
        other=uuid4(),
        when=NOW,
        colour=Colour.RED,
    )


# --- Database -----------------------------------------------------------------------------


def database_url_for(server_url: str, database: str) -> str:
    """The URL of another database on the same server."""
    return make_url(server_url).set(database=database).render_as_string(hide_password=False)


async def create_database(server_url: str, database: str) -> str:
    connection = await asyncpg.connect(asyncpg_dsn(server_url))
    try:
        await connection.execute(f'CREATE DATABASE "{database}"')
    finally:
        await connection.close()
    return database_url_for(server_url, database)


async def drop_database(server_url: str, database: str) -> None:
    connection = await asyncpg.connect(asyncpg_dsn(server_url))
    try:
        await connection.execute(f'DROP DATABASE IF EXISTS "{database}" WITH (FORCE)')
    finally:
        await connection.close()


def alembic_config(database_url: str) -> Config:
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.attributes["database_url"] = database_url
    config.attributes["configure_logging"] = False
    return config


def migrate(database_url: str, revision: str = "head") -> None:
    """``alembic upgrade``; must run outside an event loop (env.py starts its own)."""
    command.upgrade(alembic_config(database_url), revision)


def downgrade(database_url: str, revision: str = "base") -> None:
    command.downgrade(alembic_config(database_url), revision)


class DatabaseProxy:
    """A TCP proxy in front of the test database that can simulate an outage.

    ``url`` points at the proxy. :meth:`cut` drops every connection and refuses new
    ones, as a restarting server would; :meth:`restore` accepts them again on the
    same port.
    """

    def __init__(self, database_url: str) -> None:
        url = make_url(database_url)
        self._target = (url.host or "127.0.0.1", url.port or 5432)
        self._database_url = database_url
        self._port = 0
        self._server: asyncio.Server | None = None
        self._writers: set[asyncio.StreamWriter] = set()

    @property
    def url(self) -> str:
        return (
            make_url(self._database_url)
            .set(host="127.0.0.1", port=self._port)
            .render_as_string(hide_password=False)
        )

    async def __aenter__(self) -> Self:
        await self.restore()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self.cut()

    async def restore(self) -> None:
        self._server = await asyncio.start_server(self._forward, "127.0.0.1", self._port)
        self._port = self._server.sockets[0].getsockname()[1]

    async def cut(self) -> None:
        if self._server is None:
            return
        self._server.close()
        for writer in tuple(self._writers):
            writer.transport.abort()
        await self._server.wait_closed()
        self._server = None

    async def _forward(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            upstream_reader, upstream_writer = await asyncio.open_connection(*self._target)
        except OSError:
            writer.transport.abort()
            return
        self._writers |= {writer, upstream_writer}
        try:
            await asyncio.gather(_pipe(reader, upstream_writer), _pipe(upstream_reader, writer))
        finally:
            self._writers -= {writer, upstream_writer}


async def _pipe(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    try:
        while data := await reader.read(65536):
            writer.write(data)
            await writer.drain()
    except OSError:
        pass
    finally:
        writer.transport.abort()


# --- Mails --------------------------------------------------------------------------------


def token_from(mail: OutgoingMail) -> str:
    """The one-time token in the link of ``mail``."""
    match = _TOKEN_IN_LINK.search(mail.text)
    assert match is not None, f"no token link in mail {mail.subject!r}"
    return match.group(1)


def mails_to(mailer: InMemoryMailer, address: str) -> list[OutgoingMail]:
    return [mail for mail in mailer.sent if mail.to == address]


async def eventually[T](
    probe: Callable[[], Awaitable[T | None]], *, within: float = 5.0, interval: float = 0.02
) -> T:
    """Poll ``probe`` until it returns something other than ``None``."""
    async with asyncio.timeout(within):
        while True:
            result = await probe()
            if result is not None:
                return result
            await asyncio.sleep(interval)


# --- Server-Sent Events over plain ASGI ---------------------------------------------------
# httpx' ASGITransport waits for the whole response body, which never ends for an event
# stream. This reader drives the ASGI app directly and disconnects when asked to.


@dataclass(frozen=True, slots=True)
class SseMessage:
    event: str | None
    id: str | None
    data: str | None
    comment: str | None


def parse_sse_block(block: str) -> SseMessage:
    fields: dict[str, list[str]] = {}
    for line in block.split("\n"):
        name, _, value = line.partition(":")
        fields.setdefault(name, []).append(value.removeprefix(" "))
    return SseMessage(
        event=_single(fields.get("event")),
        id=_single(fields.get("id")),
        data="\n".join(fields["data"]) if "data" in fields else None,
        comment=_single(fields.get("")),
    )


def _single(values: list[str] | None) -> str | None:
    return values[-1] if values else None


@dataclass
class EventStream:
    """``async with EventStream(app, path, headers) as stream: await stream.next_event()``."""

    app: ASGIApp
    path: str
    headers: dict[str, str] = field(default_factory=dict)
    status: int | None = None
    response_headers: dict[str, str] = field(default_factory=dict)
    _messages: asyncio.Queue[SseMessage] = field(default_factory=asyncio.Queue)
    _started: asyncio.Event = field(default_factory=asyncio.Event)
    _disconnect: asyncio.Event = field(default_factory=asyncio.Event)
    _buffer: str = ""
    _task: asyncio.Task[None] | None = None

    async def __aenter__(self) -> Self:
        self._task = asyncio.create_task(self._run())
        async with asyncio.timeout(5):
            await self._started.wait()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self._disconnect.set()
        if self._task is not None:
            async with asyncio.timeout(5):
                await self._task

    async def next_message(self, *, within: float = 5.0) -> SseMessage:
        async with asyncio.timeout(within):
            return await self._messages.get()

    async def next_event(self, *, within: float = 5.0) -> SseMessage:
        """The next message that is not a heartbeat comment."""
        async with asyncio.timeout(within):
            while (message := await self._messages.get()).event is None:
                pass
        return message

    async def wait_closed(self, *, within: float = 5.0) -> None:
        """Wait until the server has ended the stream on its own."""
        assert self._task is not None
        async with asyncio.timeout(within):
            await asyncio.shield(self._task)

    def received_events(self) -> list[SseMessage]:
        """The messages received so far that are not heartbeat comments."""
        messages: list[SseMessage] = []
        while not self._messages.empty():
            message = self._messages.get_nowait()
            if message.event is not None:
                messages.append(message)
        return messages

    async def _run(self) -> None:
        path, _, query = self.path.partition("?")
        scope = {
            "type": "http",
            "asgi": {"version": "3.0", "spec_version": "2.3"},
            "http_version": "1.1",
            "method": "GET",
            "scheme": "https",
            "path": path,
            "raw_path": path.encode(),
            "root_path": "",
            "query_string": query.encode(),
            "headers": [(k.lower().encode(), v.encode()) for k, v in self.headers.items()],
            "client": ("127.0.0.1", 50000),
            "server": ("shop.test", 443),
            "state": {},
        }
        requested = False

        async def receive() -> Message:
            nonlocal requested
            if not requested:
                requested = True
                return {"type": "http.request", "body": b"", "more_body": False}
            await self._disconnect.wait()
            return {"type": "http.disconnect"}

        async def send(message: Message) -> None:
            if message["type"] == "http.response.start":
                self.status = message["status"]
                self.response_headers = {
                    k.decode().lower(): v.decode() for k, v in message["headers"]
                }
                self._started.set()
            elif message["type"] == "http.response.body":
                self._feed(message.get("body", b"").decode())

        with contextlib.suppress(asyncio.CancelledError):
            await self.app(scope, receive, send)
        self._started.set()

    def _feed(self, chunk: str) -> None:
        self._buffer += chunk.replace("\r\n", "\n")
        while "\n\n" in self._buffer:
            block, self._buffer = self._buffer.split("\n\n", 1)
            if block:
                self._messages.put_nowait(parse_sse_block(block))
