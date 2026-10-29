#!/usr/bin/env python3
"""End-to-end smoke test of the running stack: ``make smoke`` (after ``make up``).

Drives the demos of steps 2 to 4 through Caddy the way the browser does: start page,
registration, verification mail in Mailpit, verification with login, logout, password
reset, staff login and the live event stream of the "Stellwerk"; then a product with
gauge and variants, a photo uploaded straight into the object storage with a signed
URL, its sizes appearing live, publishing and the shop's pages sorted by scale (with
the maintenance of scales); then the sale of step
4: cart, a guest order with Idempotency-Key, a declined and a successful test payment,
the order joining the account once the guest registers, dispatch and a cancellation
with refund; the fairs: a fair on the "Termine" page with its calendar file, the fair
news with double opt-in and its one announcement, and the imprint from the
configuration - plus the boundaries that keep it safe: shop and admin sessions do not
mix, state-changing requests without the CSRF header are refused, and the storage
takes only signed uploads.

Every step prints one German line with ✓ or ✗. The first failure ends the run with
exit code 1, because later steps build on earlier ones.

Standard library only (Python 3.13), so it runs on any host without installing
anything. The staff credentials come from SMOKE_STAFF_EMAIL and SMOKE_STAFF_PASSWORD;
`make smoke` creates a throwaway staff account for each run and hands over Caddy's
internal root certificate with --ca-file.
"""

# The report on stdout is what this script is for.
# ruff: noqa: T201

import argparse
import hashlib
import ipaddress
import json
import os
import queue
import re
import secrets
import ssl
import struct
import sys
import threading
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request
import uuid
import zlib
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from email.message import Message
from http import HTTPStatus
from http.cookies import Morsel, SimpleCookie
from typing import IO, Any, Final

API: Final = "/api/v1"
STORE: Final = f"{API}/store/account"
ADMIN_AUTH: Final = f"{API}/admin/auth"
ADMIN_EVENTS: Final = f"{API}/admin/events"
ADMIN: Final = f"{API}/admin"
INVENTORY: Final = f"{ADMIN}/inventory"
SHOP: Final = f"{API}/store"

CLIENT_HEADER: Final = "X-Modellbahn-Client"
IDEMPOTENCY_HEADER: Final = "Idempotency-Key"
CUSTOMER_COOKIE: Final = "mb_session"
STAFF_COOKIE: Final = "mb_admin"
CART_COOKIE: Final = "mb_cart"
# 30 days of cart lifetime plus one, so the cookie never outlives the cart by surprise.
CART_COOKIE_MAX_AGE: Final = 31 * 86400

REGISTERED: Final = "identity.customer.registered"
EMAIL_VERIFIED: Final = "identity.account.email_verified"
ASSET_READY: Final = "media.asset.ready"
PRODUCT_PUBLISHED: Final = "catalog.product.published"
ORDER_PLACED: Final = "sales.order.placed"
ORDER_PAID: Final = "sales.order.paid"
STOCK_CHANGED: Final = "inventory.stock.changed"
BACKORDERED: Final = "inventory.allocation.backordered"
FAIR_ANNOUNCED: Final = "site.fair.announced"
SMOKE_CATEGORY: Final = "smoke-test"
# The smoke product's two variants, and shipping to Germany below the free threshold.
UNPAINTED_CENTS: Final = 3490
PAINTED_CENTS: Final = 7990
QUICK_ENTRY_CENTS: Final = 4200
EBAY: Final = f"{ADMIN}/marketplace/ebay"
EBAY_CATEGORY: Final = "180250"
EBAY_MARKUP_PERCENT: Final = 10
# The buyer of the built-in test marketplace (MB_EBAY_MODE=test).
EBAY_TEST_BUYER: Final = "testkauf@example.com"
EBAY_ACCOUNT_DELETION: Final = "/api/v1/webhooks/ebay/account-deletion"
SHIPPING_DE_CENTS: Final = 590
SHIPPING_EU_CENTS: Final = 1690
EU_MEMBER_STATES: Final = 27
# The smoke fair lies this far ahead, so it is always still to come.
FAIR_DAYS_AHEAD: Final = 40
GUEST_TOTAL_CENTS: Final = UNPAINTED_CENTS + SHIPPING_DE_CENTS

HTTP_TIMEOUT: Final = 15.0
MAIL_TIMEOUT: Final = 30.0
# The worker adopts guest orders after the verification event; it polls the outbox.
ADOPTION_TIMEOUT: Final = 30.0
# The worker hands out stock to a paid order (sales.order.paid → allocation) and books
# it out once the order is shipped.
ALLOCATION_TIMEOUT: Final = 30.0
UNITS_LABELLED: Final = 2
EVENT_TIMEOUT: Final = 30.0
# Longer than the API's 15 s heartbeat: a silent stream for this long is broken.
STREAM_READ_TIMEOUT: Final = 45.0
# Event ids are UUIDv7 from the API container's clock, which is this machine's clock.
# The margin only covers rounding, not a skewed clock.
REPLAY_MARGIN_SECONDS: Final = 5.0

JSON_ACCEPT: Final = "application/json, application/problem+json"
PAGE_ACCEPT: Final = "text/html"


class SmokeCheckError(Exception):
    """A check did not hold. The message (German) says what was expected."""


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise SmokeCheckError(message)


# --- HTTP --------------------------------------------------------------------------------


@dataclass(frozen=True)
class Response:
    status: int
    headers: Message
    body: bytes

    @property
    def content_type(self) -> str:
        return self.headers.get_content_type()

    @property
    def text(self) -> str:
        return self.body.decode("utf-8", errors="replace")

    def json(self) -> Any:
        try:
            return json.loads(self.body)
        except ValueError:
            raise SmokeCheckError(f"Antwort ist kein JSON: {self.text[:200]!r}") from None

    def set_cookie(self, name: str) -> Morsel[str] | None:
        """The ``Set-Cookie`` of this response for cookie ``name``, if any."""
        for header in self.headers.get_all("Set-Cookie") or []:
            parsed: SimpleCookie = SimpleCookie()
            parsed.load(header)
            if name in parsed:
                return parsed[name]
        return None


def expect_status(response: Response, status: int, what: str) -> None:
    if response.status != status:
        hint = ""
        if response.status == HTTPStatus.TOO_MANY_REQUESTS:
            # Each run logs in and registers about 15 times from the same address.
            hint = (
                " (Anmeldebremse: mehrere Läufe kurz hintereinander. Warten, "
                "MB_AUTH_RATE_LIMIT in .env erhöhen oder die API neu starten.)"
            )
        raise SmokeCheckError(
            f"{what}: erwartet HTTP {status}, erhalten {response.status}{hint}: "
            f"{response.text[:300]}"
        )


def expect_problem(response: Response, status: int, code: str, what: str) -> None:
    """An RFC 9457 problem with the given status and ``code``."""
    expect_status(response, status, what)
    expect(
        response.content_type == "application/problem+json",
        f"{what}: Content-Type ist {response.content_type}, nicht application/problem+json",
    )
    problem = response.json()
    missing = [key for key in ("type", "title", "status", "detail", "code") if key not in problem]
    expect(not missing, f"{what}: Problem ohne Felder {missing}: {problem}")
    expect(problem["status"] == status, f"{what}: Feld status ist {problem['status']}")
    expect(problem["code"] == code, f"{what}: code ist {problem['code']!r}, erwartet {code!r}")


def expect_session_cookie(
    response: Response, name: str, *, same_site: str, max_age: int, what: str
) -> str:
    """Checks the flags of a freshly set session cookie and returns its value."""
    cookie = response.set_cookie(name)
    if cookie is None or cookie.value == "":
        raise SmokeCheckError(f"{what}: kein Cookie {name} gesetzt")
    expect(bool(cookie["httponly"]), f"{what}: {name} ist nicht HttpOnly")
    expect(bool(cookie["secure"]), f"{what}: {name} ist nicht Secure")
    expect(
        cookie["samesite"].lower() == same_site,
        f"{what}: {name} hat SameSite={cookie['samesite']!r}, erwartet {same_site!r}",
    )
    expect(cookie["path"] == "/", f"{what}: {name} hat Path={cookie['path']!r}")
    expect(
        cookie["max-age"] == str(max_age),
        f"{what}: {name} hat Max-Age={cookie['max-age']!r}, erwartet {max_age}",
    )
    return cookie.value


class _NoRedirects(urllib.request.HTTPRedirectHandler):
    """Redirects are among the things checked (proxy.ts), so none is followed."""

    def redirect_request(self, *_args: object, **_kwargs: object) -> None:
        return None


def build_opener(context: ssl.SSLContext) -> urllib.request.OpenerDirector:
    return urllib.request.build_opener(
        # The stack runs on this machine: a proxy configured in HTTP(S)_PROXY must not
        # see (or break) these requests.
        urllib.request.ProxyHandler({}),
        urllib.request.HTTPSHandler(context=context),
        _NoRedirects(),
    )


def tls_context(base_url: str, ca_file: str | None) -> ssl.SSLContext:
    """Verifies against Caddy's root certificate when given one.

    Without ``--ca-file`` there is no way to verify the certificate of Caddy's internal
    CA, which exists only inside the caddy-data volume. Only then, and only for a
    loopback address, is verification switched off - this is the local development
    stack, never a server reached over a network.
    """
    if ca_file is not None:
        return ssl.create_default_context(cafile=ca_file)
    host = urllib.parse.urlsplit(base_url).hostname or ""
    if not _is_loopback(host):
        raise SmokeCheckError(
            f"{host} ist kein lokaler Rechner: ohne --ca-file wird nicht getestet"
        )
    context = ssl.create_default_context()
    # Deliberately unverified: Caddy's internal CA on localhost (see docstring).
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    return context


def _is_loopback(host: str) -> bool:
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


class Browser:
    """One visitor with its own cookies, which it sends back like a browser would.

    Requests behave like the frontend's fetcher: JSON bodies, and the CSRF header on
    state-changing methods unless a check leaves it out on purpose.
    """

    def __init__(self, base_url: str, opener: urllib.request.OpenerDirector) -> None:
        self.base_url = base_url
        self.cookies: dict[str, str] = {}
        self._opener = opener

    def page(self, path: str, *, cookies: Mapping[str, str] | None = None) -> Response:
        return self._send("GET", path, accept=PAGE_ACCEPT, cookies=cookies)

    def api(
        self,
        method: str,
        path: str,
        body: Mapping[str, object] | None = None,
        *,
        client_header: bool = True,
        cookies: Mapping[str, str] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> Response:
        sent = dict(headers or {})
        if client_header and method in {"POST", "PUT", "PATCH", "DELETE"}:
            sent[CLIENT_HEADER] = "web"
        return self._send(
            method, path, accept=JSON_ACCEPT, body=body, headers=sent, cookies=cookies
        )

    def upload(self, url: str, data: bytes, headers: Mapping[str, str]) -> Response:
        """PUT raw bytes to a signed storage URL, as the admin area's upload does."""
        parts = urllib.parse.urlsplit(url)
        expect(
            f"{parts.scheme}://{parts.netloc}" == self.base_url,
            f"Upload-URL zeigt nicht auf {self.base_url}: {url[:120]}",
        )
        path = parts.path + (f"?{parts.query}" if parts.query else "")
        request = self._request("PUT", path, headers=dict(headers), cookies={}, data=data)
        try:
            with self._opener.open(request, timeout=HTTP_TIMEOUT) as raw:
                return Response(raw.status, raw.headers, raw.read())
        except urllib.error.HTTPError as error:
            with error:
                return Response(error.code, error.headers, error.read())

    def open_stream(self, path: str, *, last_event_id: str | None = None) -> "EventStream":
        headers = {"Accept": "text/event-stream", "Cache-Control": "no-cache"}
        if last_event_id is not None:
            headers["Last-Event-ID"] = last_event_id
        request = self._request("GET", path, headers=headers, cookies=None)
        try:
            raw = self._opener.open(request, timeout=STREAM_READ_TIMEOUT)
        except urllib.error.HTTPError as error:
            with error:
                body = error.read()
            raise SmokeCheckError(
                f"Ereignisstrom: HTTP {error.code}: {body.decode(errors='replace')[:300]}"
            ) from None
        except urllib.error.URLError as error:
            raise SmokeCheckError(
                f"Keine Verbindung zu {request.full_url}: {error.reason}"
            ) from None
        content_type = raw.headers.get_content_type()
        if content_type != "text/event-stream":
            raw.close()
            raise SmokeCheckError(f"Ereignisstrom: Content-Type ist {content_type}")
        return EventStream(raw)

    def _send(
        self,
        method: str,
        path: str,
        *,
        accept: str,
        body: Mapping[str, object] | None = None,
        headers: Mapping[str, str] | None = None,
        cookies: Mapping[str, str] | None,
    ) -> Response:
        all_headers = {"Accept": accept, **(headers or {})}
        data = None
        if body is not None:
            data = json.dumps(body).encode()
            all_headers["Content-Type"] = "application/json"
        request = self._request(method, path, headers=all_headers, cookies=cookies, data=data)
        try:
            with self._opener.open(request, timeout=HTTP_TIMEOUT) as raw:
                response = Response(raw.status, raw.headers, raw.read())
        except urllib.error.HTTPError as error:
            with error:
                response = Response(error.code, error.headers, error.read())
        except urllib.error.URLError as error:
            raise SmokeCheckError(
                f"Keine Verbindung zu {request.full_url}: {error.reason}"
            ) from None
        if cookies is None:
            self._store_cookies(response)
        return response

    def _request(
        self,
        method: str,
        path: str,
        *,
        headers: Mapping[str, str],
        cookies: Mapping[str, str] | None,
        data: bytes | None = None,
    ) -> urllib.request.Request:
        request = urllib.request.Request(  # noqa: S310 - scheme checked in parse_settings
            self.base_url + path, data=data, method=method, headers=dict(headers)
        )
        # Explicit cookies replace the jar for one request (realm checks); they are
        # not stored either, so the jar stays the visitor's own.
        jar = self.cookies if cookies is None else cookies
        if jar:
            request.add_header("Cookie", "; ".join(f"{k}={v}" for k, v in jar.items()))
        return request

    def _store_cookies(self, response: Response) -> None:
        for header in response.headers.get_all("Set-Cookie") or []:
            parsed: SimpleCookie = SimpleCookie()
            parsed.load(header)
            for name, morsel in parsed.items():
                if morsel.value == "" or morsel["max-age"] == "0":
                    self.cookies.pop(name, None)
                else:
                    self.cookies[name] = morsel.value


# --- Server-Sent Events ------------------------------------------------------------------


@dataclass(frozen=True)
class ServerSentEvent:
    id: str
    event: str
    data: str

    def json(self) -> dict[str, Any]:
        try:
            value = json.loads(self.data)
        except ValueError:
            raise SmokeCheckError(
                f"Ereignis {self.id}: data ist kein JSON: {self.data!r}"
            ) from None
        expect(isinstance(value, dict), f"Ereignis {self.id}: data ist kein JSON-Objekt")
        return value  # type: ignore[no-any-return]


class EventStream:
    """Reads a text/event-stream response in a background thread.

    A read that times out leaves Python's socket file unusable, so waiting with a
    deadline happens on a queue instead. The reader is a daemon thread: the
    connection ends when this script ends.
    """

    def __init__(self, response: IO[bytes]) -> None:
        self._events: queue.Queue[ServerSentEvent | BaseException | None] = queue.Queue()
        self.heartbeats = 0
        threading.Thread(target=self._read, args=(response,), daemon=True, name="sse").start()

    def wait_for(
        self, predicate: Callable[[ServerSentEvent], bool], *, what: str
    ) -> ServerSentEvent:
        deadline = time.monotonic() + EVENT_TIMEOUT
        seen: list[str] = []
        while (remaining := deadline - time.monotonic()) > 0:
            try:
                item = self._events.get(timeout=remaining)
            except queue.Empty:
                break
            if item is None:
                raise SmokeCheckError(f"{what}: der Server hat den Ereignisstrom beendet")
            if isinstance(item, BaseException):
                raise SmokeCheckError(f"{what}: Lesefehler im Ereignisstrom: {item!r}")
            if predicate(item):
                return item
            seen.append(item.event)
        raise SmokeCheckError(
            f"{what}: nach {EVENT_TIMEOUT:.0f} s nicht angekommen (gesehen: {seen or 'nichts'})"
        )

    def _read(self, response: IO[bytes]) -> None:
        event_id, event_type = "", "message"
        data: list[str] = []
        try:
            for raw_line in response:
                line = raw_line.decode("utf-8").rstrip("\r\n")
                if line == "":
                    if data:
                        self._events.put(ServerSentEvent(event_id, event_type, "\n".join(data)))
                    event_type, data = "message", []
                    continue
                if line.startswith(":"):
                    self.heartbeats += 1
                    continue
                name, _, value = line.partition(":")
                value = value.removeprefix(" ")
                if name == "id":
                    event_id = value
                elif name == "event":
                    event_type = value
                elif name == "data":
                    data.append(value)
        except Exception as exc:  # handed to the waiting main thread
            self._events.put(exc)
            return
        self._events.put(None)


def uuid7_floor(unix_seconds: float) -> uuid.UUID:
    """The smallest UUIDv7 of that millisecond: every later event id sorts above it."""
    millis = int(unix_seconds * 1000)
    return uuid.UUID(int=(millis << 80) | (0x7 << 76) | (0b10 << 62))


# --- Mailpit -----------------------------------------------------------------------------


class Mailpit:
    """Reads the mails the worker sent, through Mailpit's REST API."""

    def __init__(self, base_url: str, opener: urllib.request.OpenerDirector) -> None:
        self._base_url = base_url
        self._opener = opener

    def wait_for(self, recipient: str, subject: str, *, prefix: bool = False) -> dict[str, Any]:
        """The full message to ``recipient`` with ``subject`` (or a subject starting with it,
        for subjects that carry the shop's configured name), once it has arrived."""
        deadline = time.monotonic() + MAIL_TIMEOUT
        while True:
            found = self._get("/api/v1/search", query=f'to:"{recipient}"', limit="50")
            for summary in found.get("messages") or []:
                actual = str(summary.get("Subject", ""))
                if actual == subject or (prefix and actual.startswith(subject)):
                    return self._get(f"/api/v1/message/{summary['ID']}")
            if time.monotonic() > deadline:
                subjects = [m.get("Subject") for m in found.get("messages") or []]
                raise SmokeCheckError(
                    f"Keine Mail „{subject}“ an {recipient} nach {MAIL_TIMEOUT:.0f} s "
                    f"(vorhanden: {subjects or 'keine'}). "
                    "Läuft der Worker? make logs SERVICE=worker"
                )
            time.sleep(0.5)

    def _get(self, path: str, **query: str) -> dict[str, Any]:
        url = f"{self._base_url}{path}"
        if query:
            url += f"?{urllib.parse.urlencode(query)}"
        try:
            with self._opener.open(url, timeout=HTTP_TIMEOUT) as raw:
                value = json.load(raw)
        except urllib.error.URLError as error:
            raise SmokeCheckError(f"Mailpit nicht erreichbar ({url}): {error}") from None
        expect(isinstance(value, dict), f"Mailpit: unerwartete Antwort von {url}")
        return value  # type: ignore[no-any-return]


def token_link(message: Mapping[str, Any], base_url: str, path: str) -> str:
    """The one-time token of the link to ``path`` in a mail's plain-text part."""
    text = str(message.get("Text", ""))
    match = re.search(rf"https?://\S+?{re.escape(path)}\?token=[A-Za-z0-9_\-]+", text)
    if match is None:
        raise SmokeCheckError(f"Mail „{message.get('Subject')}“ enthält keinen Link auf {path}")
    url = match.group(0)
    expect(
        url.startswith(f"{base_url}{path}?"),
        f"Link {url.split('?')[0]} zeigt nicht auf {base_url} (MB_PUBLIC_BASE_URL prüfen)",
    )
    return urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)["token"][0]


# --- The demo ----------------------------------------------------------------------------


def _unique(prefix: str) -> str:
    return f"{prefix}-{secrets.token_hex(5)}"


def sample_png(width: int = 640, height: int = 480) -> bytes:
    """A small photo-like PNG (gradient with a stripe), written with zlib alone."""
    seed = secrets.randbelow(200)
    rows = bytearray()
    for y in range(height):
        rows.append(0)  # filter type "none"
        for x in range(width):
            stripe = width // 3 < x < width // 3 + 40
            rows += (
                bytes((20, 20, 20))
                if stripe
                else bytes(((x * 255) // width, (y * 255) // height, seed))
            )

    def chunk(kind: bytes, payload: bytes) -> bytes:
        crc = zlib.crc32(kind + payload) & 0xFFFFFFFF
        return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", crc)

    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(bytes(rows), 6))
        + chunk(b"IEND", b"")
    )


EAN13_LENGTH: Final = 13


def ean13_valid(gtin: str) -> bool:
    if len(gtin) != EAN13_LENGTH or not gtin.isdigit():
        return False
    total = sum(int(digit) * (3 if index % 2 else 1) for index, digit in enumerate(gtin[:12]))
    return (10 - total % 10) % 10 == int(gtin[12])


@dataclass
class Customer:
    email: str
    display_name: str
    password: str = field(default_factory=lambda: f"Gleis-{secrets.token_urlsafe(12)}")
    account_id: str = ""


@dataclass
class Settings:
    base_url: str
    mailpit_url: str
    staff_email: str
    staff_password: str
    owner_email: str
    owner_password: str
    ca_file: str | None


class Demo:
    """The steps of the demo, in order. Each returns an optional detail for the log."""

    def __init__(self, settings: Settings) -> None:
        opener = build_opener(tls_context(settings.base_url, settings.ca_file))
        self.base_url = settings.base_url
        self.staff_email = settings.staff_email
        self.staff_password = settings.staff_password
        self.owner_email = settings.owner_email
        self.owner_password = settings.owner_password
        self.visitor = Browser(settings.base_url, opener)
        self.customer_browser = Browser(settings.base_url, opener)
        self.staff_browser = Browser(settings.base_url, opener)
        # Connects eBay: only the owner may.
        self.owner_browser = Browser(settings.base_url, opener)
        self.mailpit = Mailpit(settings.mailpit_url, opener)
        tag = _unique("smoke")
        self.customer = Customer(email=f"{tag}@example.com", display_name=f"Smoke {tag[-10:]}")
        self.live_customer = Customer(
            email=f"{tag}-live@example.com", display_name=f"Live {tag[-10:]}"
        )
        # Orders first as a guest, registers afterwards and finds the order in the account.
        self.buyer = Customer(email=f"{tag}-kauf@example.com", display_name=f"Kauf {tag[-10:]}")
        # Signs up for the fair news.
        self.fan = f"{tag}-messe@example.com"
        self.guest_browser = Browser(settings.base_url, opener)
        self.buyer_browser = Browser(settings.base_url, opener)
        self.started_at = time.time()
        self.stream: EventStream | None = None
        # Handed from one step to the next.
        self._verify_token = ""
        self._reset_token = ""
        self._old_password = ""
        self._product: dict[str, Any] = {}
        self._etag = ""
        self._asset: dict[str, Any] = {}
        self._product_name = f"Smoke-Stellwerk {tag[-6:]}"
        self._order: dict[str, Any] = {}
        self._account_order: dict[str, Any] = {}
        self._compartment = ""
        self._units: list[str] = []
        self._fair: dict[str, Any] = {}
        self._leave_token = ""
        self._ebay_external = ""
        self._ebay_product: dict[str, Any] = {}
        self._ebay_order: dict[str, Any] = {}

    def steps(self) -> list[tuple[str, Callable[[], str | None]]]:
        return [
            ("Startseite antwortet (200, deutsch, mit Content-Security-Policy)", self.home_page),
            ("Health-Checks /healthz und /readyz über Caddy", self.health),
            ("Kunde registriert sich (202)", self.register),
            ("Zweite Registrierung derselben Adresse: identische Antwort", self.register_again),
            ("Bestätigungsmail ist in Mailpit angekommen", self.verification_mail),
            (
                "Bestätigung nur mit Passwort: falsches 400, richtiges 200 mit mb_session",
                self.verify,
            ),
            ("GET /me liefert das bestätigte Konto", self.me),
            ("„Mein Konto“ nur mit Sitzung, sonst Umleitung zur Anmeldung", self.account_page),
            ("Abmelden: 204, Cookie gelöscht, Sitzung ungültig", self.logout),
            ("Erneute Anmeldung: 200 mit neuer Sitzung", self.login),
            ("Passwort vergessen: 202, Mail mit Link kommt an", self.password_reset_mail),
            ("Neues Passwort per Link: 204, alle Sitzungen beendet", self.password_reset),
            ("Anmeldung nur noch mit dem neuen Passwort", self.login_after_reset),
            ("Hinweismail „Passwort geändert“ kommt an", self.password_changed_mail),
            ("Mitarbeiter meldet sich im Admin-Bereich an (mb_admin)", self.staff_login),
            ("Stellwerk /admin nur mit Admin-Sitzung", self.admin_page),
            ("Ereignisstrom mit Last-Event-ID spielt die Registrierung nach", self.replay),
            ("Neue Registrierung erscheint live im Ereignisstrom", self.live_event),
            ("Katalog: Produktentwurf mit ETag, PATCH nur mit If-Match", self.product_draft),
            ("Maßstab H0 mit zwei Varianten, SKU und interner EAN", self.variants),
            ("Speicher nimmt nur signierte Uploads an (403)", self.unsigned_upload),
            ("Foto: Ticket, signierter PUT über Caddy, Abschluss", self.upload_photo),
            ("Bildstufen erscheinen live (media.asset.ready)", self.photo_ready),
            ("Bildstufen öffentlich unter /medien, Cache-Control immutable", self.renditions),
            ("Veröffentlichen mit If-Match, Ereignis im Stellwerk", self.publish),
            ("Shop: Maßstab-Einstieg, Liste in H0, Produktseite, alte Adressen", self.shop),
            ("Maßstäbe: 1:43,5 anlegen, nach Größe einsortiert, benutzte bleiben", self.scales),
            ("Lager: Plätze, Einheiten mit Etiketten-PDF, Einlagern per Scan", self.stock),
            ("Lieferbarkeit im Shop, Artikelliste für die Kasse (CSV)", self.availability),
            ("Warenkorb: Cookie mb_cart, Preise und Versand vom Server", self.cart),
            ("Kasse: falsche erwartete Summe wird abgelehnt (409 price_changed)", self.price_check),
            ("Gastbestellung mit Idempotency-Key, keine Doppelbestellung", self.guest_order),
            ("Eingangsbestätigung mit Zahlungslink kommt an", self.receipt_mail),
            ("Statusseite /bestellung/… ohne Konto, nicht für Suchmaschinen", self.status_page),
            ("Testzahlung: abgelehnt, Dienst gestört (503), dann bezahlt", self.payments),
            ("Zahlungsmail kommt an, Ereignis sales.order.paid im Stellwerk", self.paid_mail),
            ("Gast registriert sich: Bestellung erscheint im Konto", self.adoption),
            ("Versand erst nach dem Kommissionieren (409), Pickliste vom Worker", self.pick_list),
            ("Kommissionieren per Scan, live im Ereignisstrom", self.pick),
            ("Stellwerk: Bestellung finden und versenden, Versandmail", self.ship),
            ("Kundenbestellung speichert die Adresse im Adressbuch", self.account_order),
            ("Auf Bestellung: Stück wird zur Fertigung vorgemerkt", self.backorder),
            ("Stornieren erstattet die Zahlung, Stornomail", self.cancel),
            ("Seiten /konto/bestellungen und /admin/bestellungen", self.order_pages),
            ("Archivieren nimmt das Produkt aus dem Shop", self.archive),
            (
                "Schnellerfassung: Entwurf in Farbe mit Foto, zweite Farbe, veröffentlichen",
                self.quick_entry,
            ),
            (
                "eBay (Testmarktplatz): verbinden, anbieten, Kauf wird bezahlte Bestellung",
                self.ebay_sale,
            ),
            (
                "eBay: Storno nur über eBay, Shop folgt; Trennen beendet die Angebote",
                self.ebay_cancel,
            ),
            (
                "eBay-Löschmeldung: Adresse geprüft, Fälschung abgewiesen, Käuferdaten weg",
                self.ebay_account_deletion,
            ),
            ("Messe anlegen: unter /termine und als Kalenderdatei (.ics)", self.fair),
            (
                "Messe-Post: Anmeldung, Link aus Mailpit, Bestätigung (Double-Opt-in)",
                self.fair_news,
            ),
            ("Ankündigung einmal an alle Bestätigten, Ereignis im Stellwerk", self.announce),
            ("Abmelden per Link aus der Ankündigung, Messe löschen", self.fair_news_leave),
            ("Impressum aus der Konfiguration, Versand in alle EU-Länder", self.imprint),
            ("So entsteht ein Modell: Explosionszeichnung mit Stückliste", self.making_of),
            ("Kunden-Sitzung wird im Admin-Bereich abgelehnt (401)", self.customer_on_admin),
            ("Admin-Sitzung wird im Shop abgelehnt (401)", self.staff_on_store),
            ("Ohne X-Modellbahn-Client: 403 problem+json", self.csrf),
            ("Mitarbeiter meldet sich ab (204)", self.staff_logout),
            ("Kunde löscht sein Konto, Anmeldung danach abgelehnt", self.delete_account),
        ]

    # Shop ----------------------------------------------------------------------------

    def home_page(self) -> str | None:
        response = self.visitor.page("/")
        expect_status(response, 200, "GET /")
        expect('<html lang="de"' in response.text, 'Startseite ohne <html lang="de">')
        expect(
            "Jedes Modell ein Unikat" in response.text,
            "Startseite ohne „Jedes Modell ein Unikat …“",
        )
        policy = response.headers.get("content-security-policy", "")
        for directive in ("default-src 'self'", "frame-ancestors 'none'", "object-src 'none'"):
            expect(directive in policy, f"Content-Security-Policy ohne {directive!r}: {policy!r}")
        return None

    def health(self) -> str | None:
        for path in ("/healthz", "/readyz"):
            response = self.visitor.api("GET", path)
            expect_status(response, 200, f"GET {path}")
            expect(response.json() == {"status": "ok"}, f"{path}: {response.text}")
        return None

    def _register(self, customer: Customer) -> Response:
        return self.visitor.api(
            "POST",
            f"{STORE}/register",
            {
                "email": customer.email,
                "password": customer.password,
                "display_name": customer.display_name,
            },
        )

    def register(self) -> str | None:
        response = self._register(self.customer)
        expect_status(response, 202, "Registrierung")
        expect(
            response.json() == {"status": "pending_verification"},
            f"Registrierung: unerwartete Antwort {response.text}",
        )
        return self.customer.email

    def register_again(self) -> str | None:
        response = self._register(self.customer)
        expect_status(response, 202, "Zweite Registrierung")
        expect(
            response.json() == {"status": "pending_verification"},
            f"Zweite Registrierung verrät das bestehende Konto: {response.text}",
        )
        return None

    def verification_mail(self) -> str | None:
        message = self.mailpit.wait_for(self.customer.email, "Bitte bestätige deine E-Mail-Adresse")
        self._verify_token = token_link(message, self.base_url, "/konto/bestaetigen")
        page = self.customer_browser.page(
            f"/konto/bestaetigen?{urllib.parse.urlencode({'token': self._verify_token})}"
        )
        expect_status(page, 200, "Seite /konto/bestaetigen")
        return "Link führt auf /konto/bestaetigen"

    def verify(self) -> str | None:
        # Whoever clicks the link must also know the password chosen at registration;
        # otherwise a stranger could register someone else's address and take over
        # the account as soon as its owner clicks. A wrong password keeps the link.
        wrong = self.visitor.api(
            "POST",
            f"{STORE}/email-verification",
            {"token": self._verify_token, "password": "Falsches Passwort 123"},
        )
        expect_problem(wrong, 400, "invalid_password", "Bestätigung mit falschem Passwort")
        response = self.customer_browser.api(
            "POST",
            f"{STORE}/email-verification",
            {"token": self._verify_token, "password": self.customer.password},
        )
        expect_status(response, 200, "E-Mail-Bestätigung")
        expect_session_cookie(
            response, CUSTOMER_COOKIE, same_site="lax", max_age=30 * 86400, what="Bestätigung"
        )
        account = response.json()
        expect(account.get("email") == self.customer.email, f"Konto: {account}")
        expect(account.get("email_verified") is True, "Konto ist nicht als bestätigt markiert")
        self.customer.account_id = account["id"]
        again = self.visitor.api(
            "POST",
            f"{STORE}/email-verification",
            {"token": self._verify_token, "password": self.customer.password},
        )
        expect_problem(again, 400, "invalid_token", "Zweite Einlösung desselben Tokens")
        return f"Konto {self.customer.account_id}"

    def me(self) -> str | None:
        response = self.customer_browser.api("GET", f"{STORE}/me")
        expect_status(response, 200, "GET /me")
        account = response.json()
        expect(account.get("id") == self.customer.account_id, f"/me: falsches Konto {account}")
        expect(account.get("display_name") == self.customer.display_name, f"/me: {account}")
        leaked = {"password_hash", "password", "token"} & set(account)
        expect(not leaked, f"/me enthält {leaked}")
        return None

    def account_page(self) -> str | None:
        page = self.customer_browser.page("/konto")
        expect_status(page, 200, "/konto mit Sitzung")
        expect("Mein Konto" in page.text, "/konto zeigt nicht „Mein Konto“")
        anonymous = self.visitor.page("/konto")
        expect(anonymous.status in {307, 308}, f"/konto ohne Sitzung: HTTP {anonymous.status}")
        location = anonymous.headers.get("Location", "")
        expect(location.startswith("/konto/anmelden"), f"/konto leitet nach {location!r} um")
        return None

    def logout(self) -> str | None:
        token = self.customer_browser.cookies[CUSTOMER_COOKIE]
        response = self.customer_browser.api("DELETE", f"{STORE}/session")
        expect_status(response, 204, "Abmelden")
        cleared = response.set_cookie(CUSTOMER_COOKIE)
        expect(
            cleared is not None and cleared["max-age"] == "0", "Abmelden löscht mb_session nicht"
        )
        expect(CUSTOMER_COOKIE not in self.customer_browser.cookies, "Cookie noch vorhanden")
        stale = self.visitor.api("GET", f"{STORE}/me", cookies={CUSTOMER_COOKIE: token})
        expect_problem(stale, 401, "not_authenticated", "GET /me mit der alten Sitzung")
        return None

    def _login(self, password: str) -> Response:
        return self.customer_browser.api(
            "POST", f"{STORE}/session", {"email": self.customer.email, "password": password}
        )

    def login(self) -> str | None:
        response = self._login(self.customer.password)
        expect_status(response, 200, "Anmeldung")
        expect_session_cookie(
            response, CUSTOMER_COOKIE, same_site="lax", max_age=30 * 86400, what="Anmeldung"
        )
        expect_status(self.customer_browser.api("GET", f"{STORE}/me"), 200, "GET /me")
        return None

    def password_reset_mail(self) -> str | None:
        response = self.visitor.api(
            "POST", f"{STORE}/password-reset", {"email": self.customer.email}
        )
        expect_status(response, 202, "Passwort vergessen")
        unknown = self.visitor.api(
            "POST", f"{STORE}/password-reset", {"email": f"{_unique('niemand')}@example.com"}
        )
        expect(
            (unknown.status, unknown.body) == (response.status, response.body),
            "Passwort vergessen: unbekannte Adresse antwortet anders (Enumeration)",
        )
        message = self.mailpit.wait_for(self.customer.email, "Neues Passwort festlegen")
        self._reset_token = token_link(message, self.base_url, "/konto/passwort-zuruecksetzen")
        return "Link führt auf /konto/passwort-zuruecksetzen"

    def password_reset(self) -> str | None:
        session = self.customer_browser.cookies[CUSTOMER_COOKIE]
        self._old_password = self.customer.password
        self.customer.password = f"Weiche-{secrets.token_urlsafe(12)}"
        response = self.visitor.api(
            "POST",
            f"{STORE}/password-reset/confirm",
            {"token": self._reset_token, "new_password": self.customer.password},
        )
        expect_status(response, 204, "Neues Passwort setzen")
        stale = self.visitor.api("GET", f"{STORE}/me", cookies={CUSTOMER_COOKIE: session})
        expect_problem(stale, 401, "not_authenticated", "Sitzung nach dem Zurücksetzen")
        return None

    def login_after_reset(self) -> str | None:
        old = self._login(self._old_password)
        expect_problem(old, 401, "invalid_credentials", "Anmeldung mit dem alten Passwort")
        new = self._login(self.customer.password)
        expect_status(new, 200, "Anmeldung mit dem neuen Passwort")
        return None

    def password_changed_mail(self) -> str | None:
        self.mailpit.wait_for(self.customer.email, "Dein Passwort wurde geändert")
        return None

    # Admin ---------------------------------------------------------------------------

    def staff_login(self) -> str | None:
        response = self.staff_browser.api(
            "POST",
            f"{ADMIN_AUTH}/session",
            {"email": self.staff_email, "password": self.staff_password},
        )
        expect_status(response, 200, "Admin-Anmeldung")
        expect_session_cookie(
            response, STAFF_COOKIE, same_site="strict", max_age=12 * 3600, what="Admin-Anmeldung"
        )
        me = self.staff_browser.api("GET", f"{ADMIN_AUTH}/me")
        expect_status(me, 200, "GET /admin/auth/me")
        staff = me.json()
        expect(staff.get("role") in {"owner", "staff", "packer"}, f"StaffOut ohne Rolle: {staff}")
        return f"{staff['display_name']} ({staff['role']})"

    def admin_page(self) -> str | None:
        page = self.staff_browser.page("/admin")
        expect_status(page, 200, "/admin mit Admin-Sitzung")
        expect("Stellwerk" in page.text, "/admin zeigt nicht das Stellwerk")
        anonymous = self.visitor.page("/admin")
        expect(anonymous.status in {307, 308}, f"/admin ohne Sitzung: HTTP {anonymous.status}")
        location = anonymous.headers.get("Location", "")
        expect(location.startswith("/admin/anmelden"), f"/admin leitet nach {location!r} um")
        return None

    def replay(self) -> str | None:
        since = uuid7_floor(self.started_at - REPLAY_MARGIN_SECONDS)
        self.stream = self.staff_browser.open_stream(ADMIN_EVENTS, last_event_id=str(since))
        account_id = self.customer.account_id
        registered = self.stream.wait_for(
            lambda e: e.event == REGISTERED and _account_of(e) == account_id,
            what=f"{REGISTERED} für {account_id}",
        )
        payload = registered.json()
        expect(payload.get("id") == registered.id, "SSE: id-Feld und data.id unterscheiden sich")
        expect(
            payload.get("data", {}).get("display_name") == self.customer.display_name,
            f"SSE: falscher Anzeigename in {payload}",
        )
        expect(self.customer.email not in registered.data, "SSE-Ereignis enthält die E-Mail")
        self.stream.wait_for(
            lambda e: e.event == EMAIL_VERIFIED and _account_of(e) == account_id,
            what=f"{EMAIL_VERIFIED} für {account_id}",
        )
        return f"Ereignis {registered.id}"

    def live_event(self) -> str | None:
        if self.stream is None:
            raise SmokeCheckError("Der Ereignisstrom aus dem vorigen Schritt fehlt")
        sent_at = time.monotonic()
        expect_status(self._register(self.live_customer), 202, "Registrierung (live)")
        name = self.live_customer.display_name
        event = self.stream.wait_for(
            lambda e: (
                e.event == REGISTERED and e.json().get("data", {}).get("display_name") == name
            ),
            what=f"Live-Ereignis für „{name}“",
        )
        return f"nach {time.monotonic() - sent_at:.1f} s ({event.id})"

    # Catalogue and media --------------------------------------------------------------

    def _staff(
        self,
        method: str,
        path: str,
        body: Mapping[str, object] | None = None,
        *,
        if_match: str | None = None,
    ) -> Response:
        if if_match is None:
            return self.staff_browser.api(method, path, body)
        return self.staff_browser._send(  # one extra header
            method,
            path,
            accept=JSON_ACCEPT,
            body=body,
            headers={CLIENT_HEADER: "web", "If-Match": if_match},
            cookies=None,
        )

    def _remember(self, response: Response) -> dict[str, Any]:
        product: dict[str, Any] = response.json()
        self._product = product
        self._etag = response.headers.get("ETag", "")
        expect(self._etag == f'"{product["version"]}"', f"ETag {self._etag!r} passt nicht")
        return product

    def _category_id(self) -> str:
        listed = self._staff("GET", f"{ADMIN}/categories")
        expect_status(listed, 200, "Kategorien lesen")
        for category in listed.json():
            if category["slug"] == SMOKE_CATEGORY:
                return str(category["id"])
        created = self._staff(
            "POST", f"{ADMIN}/categories", {"name": "Smoke-Test", "slug": SMOKE_CATEGORY}
        )
        expect_status(created, 201, "Kategorie anlegen")
        return str(created.json()["id"])

    def product_draft(self) -> str | None:
        category_id = self._category_id()
        created = self._staff("POST", f"{ADMIN}/products", {"name": self._product_name})
        expect_status(created, 201, "Produkt anlegen")
        product = self._remember(created)
        expect(product["status"] == "draft", f"Neues Produkt ist {product['status']}")
        path = f"{ADMIN}/products/{product['id']}"
        changes = {
            "summary": "Hebelstellwerk aus dem Smoke-Test",
            "primary_category_id": category_id,
            "epoch_codes": ["III"],
        }
        expect_problem(
            self._staff("PATCH", path, changes), 428, "precondition_required", "PATCH ohne If-Match"
        )
        expect_problem(
            self._staff("PATCH", path, changes, if_match='"999"'),
            412,
            "precondition_failed",
            "PATCH mit veralteter Version",
        )
        changed = self._staff("PATCH", path, changes, if_match=self._etag)
        expect_status(changed, 200, "PATCH mit If-Match")
        self._remember(changed)
        return f"{product['slug']} · ETag {self._etag}"

    def variants(self) -> str | None:
        product_id = self._product["id"]
        scale = self._staff(
            "POST",
            f"{ADMIN}/products/{product_id}/scales",
            {"scale_code": "H0", "length_mm": 112.5, "weight_g": 85},
        )
        expect_status(scale, 201, "Maßstab H0")
        scale_id = scale.json()["scales"][0]["id"]
        variants = f"{ADMIN}/product-scales/{scale_id}/variants"
        # Kits come from the shelf, finished models (in a colour) are made to order.
        for finish, color, price, made_to_order in (
            ("unpainted", "", UNPAINTED_CENTS, False),
            ("painted", "gelb", PAINTED_CENTS, True),
        ):
            variant = self._staff(
                "POST",
                variants,
                {
                    "finish_code": finish,
                    "color": color,
                    "price_cents": price,
                    "allow_backorder": made_to_order,
                },
            )
            expect_status(variant, 201, f"Variante {finish}")
        product = self._remember(variant)
        skus = [v["sku"] for v in product["scales"][0]["variants"]]
        prefix = f"MB-{product['number']:06d}-H0-"
        expect(sorted(skus) == [prefix + "B", prefix + "F"], f"SKUs {skus}")
        expect(self._variant("painted")["color"] == "Gelb", "Farbe nicht vereinheitlicht")
        # The kit has no colour, and primed is no longer offered.
        for body, wanted in (
            ({"finish_code": "unpainted", "color": "Rot"}, ("color", "not_colored")),
            ({"finish_code": "primed"}, ("finish_code", "not_offered")),
        ):
            refused = self._staff("POST", variants, {**body, "price_cents": 100})
            expect_problem(refused, 422, "validation_failed", f"Variante {body}")
            errors = [(e["field"], e["code"]) for e in refused.json()["errors"]]
            expect(errors == [wanted], f"Fehler zu {body}: {errors}")
        gtins = [v["gtin"] for v in product["scales"][0]["variants"]]
        expect(all(g.startswith("2") and ean13_valid(g) for g in gtins), f"EANs {gtins}")
        painted = self._variant("painted")
        lead_time = (painted["lead_time_min_weeks"], painted["lead_time_max_weeks"])
        expect(lead_time == (1, 2), f"Lieferzeit auf Bestellung: {lead_time}")
        return ", ".join(skus)

    def unsigned_upload(self) -> str | None:
        response = self.visitor.upload(
            f"{self.base_url}/mb-media-private/incoming/{uuid.uuid4()}/original",
            b"kein Bild",
            {"Content-Type": "image/png"},
        )
        expect(response.status == HTTPStatus.FORBIDDEN, f"Unsignierter PUT: HTTP {response.status}")
        return None

    def upload_photo(self) -> str | None:
        data = sample_png()
        ticket = self._staff(
            "POST",
            f"{ADMIN}/media/uploads",
            {
                "filename": "smoke.png",
                "mime_type": "image/png",
                "size_bytes": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
            },
        )
        expect_status(ticket, 200, "Upload-Ticket")
        body = ticket.json()
        upload = body["upload"]
        expect(upload is not None, "Upload-Ticket ohne URL (Datei schon bekannt?)")
        wrong = self.visitor.upload(upload["url"], data, {"Content-Type": "image/jpeg"})
        expect(wrong.status == HTTPStatus.FORBIDDEN, f"PUT mit anderem Typ: HTTP {wrong.status}")
        stored = self.visitor.upload(upload["url"], data, upload["headers"])
        expect_status(stored, 200, "Signierter PUT in den Speicher")
        self._asset = body["asset"]
        completed = self._staff("POST", f"{ADMIN}/media/{self._asset['id']}/complete")
        expect_status(completed, 200, "Upload abschließen")
        expect(completed.json()["status"] == "uploaded", f"Asset ist {completed.json()['status']}")
        return f"{len(data) // 1024} KiB · Asset {self._asset['id']}"

    def photo_ready(self) -> str | None:
        if self.stream is None:
            raise SmokeCheckError("Der Ereignisstrom aus den vorigen Schritten fehlt")
        asset_id = self._asset["id"]
        started = time.monotonic()
        self.stream.wait_for(
            lambda e: (
                e.event == ASSET_READY and e.json().get("data", {}).get("asset_id") == asset_id
            ),
            what=f"{ASSET_READY} für {asset_id}",
        )
        asset = self._staff("GET", f"{ADMIN}/media/{asset_id}")
        expect_status(asset, 200, "Asset lesen")
        self._asset = asset.json()
        expect(self._asset["status"] == "ready", f"Asset ist {self._asset['status']}")
        names = sorted({r["name"] for r in self._asset["renditions"]})
        return f"nach {time.monotonic() - started:.1f} s · Stufen {', '.join(names)}"

    def renditions(self) -> str | None:
        thumb = next(
            r for r in self._asset["renditions"] if r["name"] == "thumb" and r["format"] == "webp"
        )
        expect(thumb["url"].startswith("/medien/"), f"Stufen-URL {thumb['url']}")
        response = self.visitor._send(  # binary body
            "GET", thumb["url"], accept="image/webp", cookies={}
        )
        expect_status(response, 200, f"GET {thumb['url']}")
        expect(response.content_type == "image/webp", f"Content-Type {response.content_type}")
        expect(
            "immutable" in response.headers.get("Cache-Control", ""),
            f"Cache-Control {response.headers.get('Cache-Control')!r}",
        )
        expect(response.body[:4] == b"RIFF", "Thumbnail ist kein WebP")
        return f"{thumb['width']} x {thumb['height']} px"

    def publish(self) -> str | None:
        product_id = self._product["id"]
        attached = self._staff(
            "POST",
            f"{ADMIN}/products/{product_id}/media",
            {"asset_id": self._asset["id"], "alt_text": "Ansicht von vorn"},
        )
        expect_status(attached, 200, "Foto in die Galerie")
        product = self._remember(attached)
        expect(product["publish_blockers"] == [], f"Noch blockiert: {product['publish_blockers']}")
        published = self._staff(
            "POST", f"{ADMIN}/products/{product_id}/publish", if_match=self._etag
        )
        expect_status(published, 200, "Veröffentlichen")
        self._remember(published)
        if self.stream is not None:
            self.stream.wait_for(
                lambda e: (
                    e.event == PRODUCT_PUBLISHED
                    and e.json().get("data", {}).get("product_id") == product_id
                ),
                what=f"{PRODUCT_PUBLISHED} für {product_id}",
            )
        return None

    def shop(self) -> str | None:
        slug = self._product["slug"]
        listing = self.visitor.api(
            "GET", f"{SHOP}/products?{urllib.parse.urlencode({'q': self._product_name})}"
        )
        expect_status(listing, 200, "Shop-Liste")
        slugs = [item["slug"] for item in listing.json()["items"]]
        expect(slug in slugs, f"{slug} fehlt in der Shop-Liste {slugs}")
        detail = self.visitor.api("GET", f"{SHOP}/products/{slug}")
        expect_status(detail, 200, "Produktdaten im Shop")
        product = detail.json()
        expect(len(product["gallery"]) == 1, "Galerie im Shop ist leer")
        expect("gtin" not in product["scales"][0]["variants"][0], "Shop verrät die EAN")
        page = self.visitor.page(f"/produkte/{slug}?massstab=h0")
        expect_status(page, 200, f"Seite /produkte/{slug}")
        expect(self._product_name in page.text, "Produktseite ohne Produktnamen")
        expect("/medien/" in page.text, "Produktseite ohne Bild aus /medien")

        navigation = self.visitor.api("GET", f"{SHOP}/navigation").json()
        h0 = next(scale for scale in navigation["scales"] if scale["code"] == "H0")
        expect(h0["product_count"] >= 1, f"Navigation zählt in H0 {h0['product_count']} Produkte")
        category = next(c for c in navigation["categories"] if c["slug"] == SMOKE_CATEGORY)
        expect(category["product_counts"].get("H0", 0) >= 1, f"Kategorie zählt {category}")
        entry = self.visitor.page("/katalog")
        expect_status(entry, 200, "Seite /katalog")
        expect("Welcher Maßstab?" in entry.text, "/katalog ohne Maßstab-Einstieg")
        query = urllib.parse.urlencode({"suche": self._product_name})
        listed = self.visitor.page(f"/katalog/h0/{SMOKE_CATEGORY}?{query}")
        expect_status(listed, 200, f"Seite /katalog/h0/{SMOKE_CATEGORY}")
        expect(self._product_name in listed.text, "Liste in H0 ohne das Produkt")
        old = self.visitor.page(f"/katalog?spur=H0&kategorie={SMOKE_CATEGORY}")
        expect(old.status in {307, 308}, f"Alte Katalog-Adresse: HTTP {old.status}")
        location = old.headers.get("Location", "")
        expect(
            location.endswith(f"/katalog/h0/{SMOKE_CATEGORY}"),
            f"Alte Adresse leitet nach {location}",
        )
        return f"/katalog/h0/{SMOKE_CATEGORY}"

    def scales(self) -> str | None:
        code = "X" + "".join(secrets.choice("0123456789ABCDEFGHJKLMNPQRSTUVWXYZ") for _ in range(3))
        created = self._staff(
            "POST",
            f"{ADMIN}/scales",
            {"code": code, "name": f"Smoke {code}", "ratio_denominator": 43.5},
        )
        expect_status(created, 201, "Maßstab anlegen")
        expect(created.json()["ratio"] == "1:43,5", f"Verhältnis {created.json()['ratio']}")
        listed = self._staff("GET", f"{ADMIN}/scales")
        expect_status(listed, 200, "Maßstäbe lesen")
        codes = [scale["code"] for scale in listed.json()]
        expect(
            codes.index("H0") < codes.index(code) < codes.index("G"),
            f"1:43,5 steht nicht zwischen H0 und G: {codes}",
        )
        expect_problem(
            self._staff("DELETE", f"{ADMIN}/scales/H0"), 409, "scale_in_use", "Benutzter Maßstab"
        )
        expect_status(self._staff("DELETE", f"{ADMIN}/scales/{code}"), 204, "Maßstab löschen")
        return f"{code} angelegt und gelöscht"

    # Sales ---------------------------------------------------------------------------

    def _variant(self, finish: str) -> dict[str, Any]:
        variants = self._product["scales"][0]["variants"]
        return next(v for v in variants if v["finish_code"] == finish)

    def _checkout(self, browser: Browser, body: Mapping[str, object], key: str) -> Response:
        return browser.api("POST", f"{SHOP}/checkouts", body, headers={IDEMPOTENCY_HEADER: key})

    def _pay(self, method: str, key: str, token: str | None = None) -> Response:
        token = token or self._order["public_token"]
        return self.guest_browser.api(
            "POST",
            f"{SHOP}/orders/{token}/payments",
            {"method": method},
            headers={IDEMPOTENCY_HEADER: key},
        )

    def _guest_body(self, total: int) -> dict[str, object]:
        return {
            "expected_total_cents": total,
            "email": self.buyer.email,
            "address": {
                "recipient": "Erika  Mustermann",
                "street": "Bahnhofstraße 12",
                "postal_code": "38707",
                "city": "Altenau",
                "country_code": "DE",
            },
        }

    def _wait_for_order_event(self, event_type: str, number: str) -> None:
        if self.stream is not None:
            self.stream.wait_for(
                lambda e: (
                    e.event == event_type and e.json().get("data", {}).get("number") == number
                ),
                what=f"{event_type} für {number}",
            )

    def _scan(
        self, mode: str, raw: str, context: Mapping[str, str] | None = None, scan_id: str = ""
    ) -> dict[str, Any]:
        body = {
            "scan_id": scan_id or str(uuid.uuid4()),
            "raw": raw,
            "mode": mode,
            "source": "scanner",
            "context": dict(context or {}),
        }
        response = self._staff("POST", f"{INVENTORY}/scans", body)
        expect_status(response, 200, f"Scan {raw} ({mode})")
        answer: dict[str, Any] = response.json()
        return answer

    def _stock_of(self, variant_id: str) -> dict[str, Any]:
        stock = self._staff("GET", f"{INVENTORY}/stock")
        expect_status(stock, 200, "Bestand")
        line: dict[str, Any] = next(
            (item for item in stock.json()["items"] if item["variant_id"] == variant_id), {}
        )
        return line

    def _wait_for_stock_event(self, what: str, **data: str) -> None:
        if self.stream is not None:
            self.stream.wait_for(
                lambda e: (
                    e.event == STOCK_CHANGED
                    and all(e.json().get("data", {}).get(k) == v for k, v in data.items())
                ),
                what=what,
            )

    def _allocated_pick_list(self, order_id: str) -> dict[str, Any]:
        deadline = time.monotonic() + ALLOCATION_TIMEOUT
        while True:
            response = self._staff("GET", f"{INVENTORY}/orders/{order_id}/pick-list")
            expect_status(response, 200, "Pickliste")
            pick_list: dict[str, Any] = response.json()
            if pick_list["allocated"]:
                return pick_list
            if time.monotonic() > deadline:
                raise SmokeCheckError(
                    f"Bestellung nach {ALLOCATION_TIMEOUT:.0f} s nicht zugeteilt. "
                    "Läuft der Worker? make logs SERVICE=worker"
                )
            time.sleep(0.5)

    def _shipped_unit(self, code: str) -> None:
        # sales.order.shipped has two handlers: the mail can arrive before the stock is booked.
        deadline = time.monotonic() + ALLOCATION_TIMEOUT
        while True:
            unit = self._staff("GET", f"{INVENTORY}/units/{code}")
            expect_status(unit, 200, "Versendete Einheit")
            if unit.json()["status"] == "shipped":
                return
            if time.monotonic() > deadline:
                raise SmokeCheckError(
                    f"Einheit nach {ALLOCATION_TIMEOUT:.0f} s nicht versendet: "
                    f"{unit.json()['status']}. Läuft der Worker? make logs SERVICE=worker"
                )
            time.sleep(0.5)

    def stock(self) -> str | None:
        tag = secrets.token_hex(3).upper()
        site, shelf = f"SM{tag}", f"R{tag}"
        for body in (
            {"segment": site, "kind": "site", "name": "Smoke-Lager"},
            {"segment": shelf, "kind": "shelf", "parent_code": site},
            {"segment": "F01", "kind": "compartment", "parent_code": shelf, "name": "Fach 1"},
        ):
            created = self._staff("POST", f"{INVENTORY}/locations", body)
            expect_status(created, 201, f"Lagerplatz {body['segment']}")
        self._compartment = created.json()["code"]
        expect(self._compartment == f"{shelf}-F01", f"Code des Fachs: {self._compartment}")

        variant = self._variant("unpainted")
        batch = self._staff(
            "POST",
            f"{INVENTORY}/units",
            {"variant_id": variant["id"], "quantity": UNITS_LABELLED},
        )
        expect_status(batch, 201, "Einheiten erfassen")
        units = batch.json()["items"]
        expect(
            [u["status"] for u in units] == ["labeled"] * UNITS_LABELLED, f"Neue Einheiten: {units}"
        )
        self._units = [u["code"] for u in units]

        labels = self.staff_browser._send(  # a PDF, not JSON
            "POST",
            f"{INVENTORY}/labels",
            accept="application/pdf",
            body={
                "sheet": "a4_70x37",
                "skip": 3,
                "unit_codes": self._units,
                "location_codes": [self._compartment],
            },
            headers={CLIENT_HEADER: "web"},
            cookies=None,
        )
        expect_status(labels, 200, "Etiketten")
        expect(
            labels.content_type == "application/pdf" and labels.body.startswith(b"%PDF"),
            f"Etiketten sind kein PDF: {labels.content_type}",
        )

        place = {"location_code": self._compartment}
        chosen = self._scan("put_away", self._compartment)
        expect(chosen["outcome"] == "selected", f"Platz-Scan: {chosen['outcome']}")
        scan_id = str(uuid.uuid4())
        stored = self._scan("put_away", self._units[0], place, scan_id)
        expect(stored["message"] == "put_away", f"Einlagern: {stored['message']}")
        repeated = self._scan("put_away", self._units[0], place, scan_id)
        expect(repeated == stored, "Wiederholter Scan bucht anders als der erste")
        by_ean = self._scan("put_away", variant["gtin"], place)
        expect(
            by_ean["outcome"] == "applied" and by_ean["effect"]["unit_code"] == self._units[1],
            f"Einlagern per EAN: {by_ean['outcome']} {by_ean['effect']}",
        )
        self._wait_for_stock_event(
            f"{STOCK_CHANGED} für {self._units[1]}",
            unit_code=self._units[1],
            location_code=self._compartment,
        )
        line = self._stock_of(variant["id"])
        expect(line.get("in_stock") == UNITS_LABELLED, f"Bestand nach dem Einlagern: {line}")
        return f"{self._compartment}: 2 Stück, eines per Einheiten-Code, eines per EAN"

    def availability(self) -> str | None:
        slug = self._product["slug"]
        response = self.visitor.api("GET", f"{SHOP}/products/{slug}/availability")
        expect_status(response, 200, "Lieferbarkeit")
        by_variant = {item["variant_id"]: item for item in response.json()["items"]}
        unpainted = by_variant[self._variant("unpainted")["id"]]
        painted = by_variant[self._variant("painted")["id"]]
        expect(
            (unpainted["availability"], unpainted["free_units"]) == ("in_stock", UNITS_LABELLED),
            f"Bausatz: {unpainted}",
        )
        expect(
            (
                painted["availability"],
                painted["lead_time_min_weeks"],
                painted["lead_time_max_weeks"],
            )
            == ("made_to_order", 1, 2),
            f"Fertigmodell: {painted}",
        )
        articles = self.staff_browser._send(
            "GET", f"{ADMIN}/catalog/articles.csv", accept="text/csv", cookies=None
        )
        expect_status(articles, 200, "Artikelliste")
        expect(articles.content_type == "text/csv", f"Artikelliste: {articles.content_type}")
        text = articles.text
        expect(self._variant("unpainted")["gtin"] in text, "Artikelliste ohne die EAN")
        expect("auf Bestellung (1-2 Wochen)" in text, "Artikelliste ohne Lieferzeit")
        return "Bausatz sofort (2), Fertigmodell in Gelb auf Bestellung in 1 bis 2 Wochen"

    def cart(self) -> str | None:
        empty = self.guest_browser.api("GET", f"{SHOP}/cart")
        expect_status(empty, 200, "Leerer Warenkorb")
        expect(
            empty.json()["lines"] == [], f"Neuer Besucher hat einen Warenkorb: {empty.text[:200]}"
        )
        expect(empty.set_cookie(CART_COOKIE) is None, "Nur Ansehen legt schon einen Warenkorb an")
        variant = self._variant("unpainted")
        added = self.guest_browser.api("PUT", f"{SHOP}/cart/lines/{variant['id']}", {"quantity": 1})
        expect_status(added, 200, "Variante in den Warenkorb")
        expect_session_cookie(
            added, CART_COOKIE, same_site="lax", max_age=CART_COOKIE_MAX_AGE, what="Warenkorb"
        )
        too_many = self.guest_browser.api(
            "PUT", f"{SHOP}/cart/lines/{variant['id']}", {"quantity": 3}
        )
        expect_problem(too_many, 409, "insufficient_stock", "Mehr als im Lager liegt")
        cart = self.guest_browser.api("GET", f"{SHOP}/cart").json()
        expect(cart["item_count"] == 1, f"Warenkorb: {cart['item_count']} Artikel")
        totals = cart["totals"]
        expected = {
            "subtotal_cents": UNPAINTED_CENTS,
            "shipping_cents": SHIPPING_DE_CENTS,
            "total_cents": GUEST_TOTAL_CENTS,
            "tax_cents": 651,  # 19 % contained in 40,80 €
        }
        expect(totals == expected, f"Summen {totals}, erwartet {expected}")
        expect(cart["ready_for_checkout"] is True, "Warenkorb nicht bereit für die Kasse")
        return "34,90 € + 5,90 € Versand = 40,80 €"

    def price_check(self) -> str | None:
        refused = self._checkout(
            self.guest_browser, self._guest_body(UNPAINTED_CENTS), str(uuid.uuid4())
        )
        expect_problem(refused, 409, "price_changed", "Bestellung mit veralteter Summe")
        cart = self.guest_browser.api("GET", f"{SHOP}/cart").json()
        expect(cart["item_count"] == 1, "Abgelehnte Bestellung hat den Warenkorb geleert")
        return None

    def guest_order(self) -> str | None:
        key = str(uuid.uuid4())
        body = self._guest_body(GUEST_TOTAL_CENTS)
        missing_key = self.guest_browser.api("POST", f"{SHOP}/checkouts", body)
        expect_problem(missing_key, 422, "validation_failed", "Bestellung ohne Idempotency-Key")
        placed = self._checkout(self.guest_browser, body, key)
        expect_status(placed, 201, "Gastbestellung")
        order = placed.json()
        self._order = order
        expect(
            re.fullmatch(r"MB-\d{4}-\d{5}", order["number"]) is not None,
            f"Bestellnummer {order['number']}",
        )
        expect(order["status"] == "pending_payment", f"Neue Bestellung ist {order['status']}")
        expect(order["totals"]["total_cents"] == GUEST_TOTAL_CENTS, f"Summe {order['totals']}")
        expect(
            order["shipping_address"]["recipient"] == "Erika Mustermann",
            f"Empfänger nicht normalisiert: {order['shipping_address']}",
        )
        expect(placed.headers.get("Cache-Control") == "no-store", "Bestellung ist cachebar")
        replayed = self._checkout(self.guest_browser, body, key)
        expect_status(replayed, 201, "Wiederholte Bestellung")
        expect(replayed.headers.get("Idempotent-Replayed") == "true", "Kein Idempotent-Replayed")
        expect(replayed.json()["number"] == order["number"], "Wiederholung legt neue Bestellung an")
        changed = self._checkout(self.guest_browser, {**body, "email": "x@example.com"}, key)
        expect_problem(changed, 409, "idempotency_key_reused", "Gleicher Schlüssel, andere Daten")
        emptied = self.guest_browser.api("GET", f"{SHOP}/cart").json()
        expect(emptied["lines"] == [], "Warenkorb nach der Bestellung nicht leer")
        self._wait_for_order_event(ORDER_PLACED, order["number"])
        return str(order["number"])

    def receipt_mail(self) -> str | None:
        number = self._order["number"]
        message = self.mailpit.wait_for(self.buyer.email, f"Bestellung {number} eingegangen")
        text = str(message.get("Text", ""))
        link = f"{self.base_url}/bestellung/{self._order['public_token']}/bezahlen"
        expect(link in text, f"Eingangsbestätigung ohne Zahlungslink {link}")
        expect("40,80" in text, "Eingangsbestätigung ohne Summe")
        return "mit Link auf /bestellung/…/bezahlen"

    def status_page(self) -> str | None:
        token = self._order["public_token"]
        api = self.visitor.api("GET", f"{SHOP}/orders/{token}")
        expect_status(api, 200, "Bestellung über den Statuslink")
        expect(api.json()["number"] == self._order["number"], "Statuslink zeigt andere Bestellung")
        unknown = self.visitor.api("GET", f"{SHOP}/orders/{secrets.token_urlsafe(32)}")
        expect_problem(unknown, 404, "order_not_found", "Unbekannter Statuslink")
        page = self.visitor.page(f"/bestellung/{token}")
        expect_status(page, 200, "Seite /bestellung/…")
        expect('content="noindex, nofollow"' in page.text, "Statusseite ohne noindex")
        expect(
            'name="referrer" content="no-referrer"' in page.text, "Statusseite gibt Referrer weiter"
        )
        return None

    def payments(self) -> str | None:
        declined = self._pay("declined", str(uuid.uuid4()))
        expect_status(declined, 200, "Abgelehnte Zahlung")
        order = declined.json()
        expect(order["status"] == "pending_payment", f"Nach Ablehnung: {order['status']}")
        expect(order["payments"][-1]["status"] == "failed", f"Zahlungen {order['payments']}")
        down = self._pay("fails", str(uuid.uuid4()))
        expect_problem(down, 503, "payment_unavailable", "Gestörter Zahlungsdienst")
        expect(down.headers.get("Retry-After") == "30", "503 ohne Retry-After")
        key = str(uuid.uuid4())
        paid = self._pay("succeeds", key)
        expect_status(paid, 200, "Zahlung")
        order = paid.json()
        expect(order["status"] == "paid", f"Nach der Zahlung: {order['status']}")
        again = self._pay("succeeds", key)
        expect_status(again, 200, "Wiederholte Zahlung")
        captured = [p for p in again.json()["payments"] if p["status"] == "captured"]
        expect(len(captured) == 1, f"Doppelt abgebucht: {again.json()['payments']}")
        expect_problem(
            self._pay("succeeds", str(uuid.uuid4())), 409, "order_not_payable", "Zweite Zahlung"
        )
        self._order = order
        return f"{len(order['payments'])} Zahlungsversuche, einmal abgebucht"

    def paid_mail(self) -> str | None:
        number = self._order["number"]
        self.mailpit.wait_for(self.buyer.email, f"Zahlung eingegangen: Bestellung {number}")
        self._wait_for_order_event(ORDER_PAID, number)
        return None

    def adoption(self) -> str | None:
        registered = self.visitor.api(
            "POST",
            f"{STORE}/register",
            {
                "email": self.buyer.email,
                "password": self.buyer.password,
                "display_name": self.buyer.display_name,
            },
        )
        expect_status(registered, 202, "Registrierung des Gasts")
        message = self.mailpit.wait_for(self.buyer.email, "Bitte bestätige deine E-Mail-Adresse")
        token = token_link(message, self.base_url, "/konto/bestaetigen")
        verified = self.buyer_browser.api(
            "POST", f"{STORE}/email-verification", {"token": token, "password": self.buyer.password}
        )
        expect_status(verified, 200, "Bestätigung des Gasts")
        number = self._order["number"]
        deadline = time.monotonic() + ADOPTION_TIMEOUT
        while True:
            listed = self.buyer_browser.api("GET", f"{STORE}/orders")
            expect_status(listed, 200, "Bestellungen im Konto")
            numbers = [item["number"] for item in listed.json()["items"]]
            if number in numbers:
                break
            if time.monotonic() > deadline:
                raise SmokeCheckError(
                    f"{number} nach {ADOPTION_TIMEOUT:.0f} s nicht im Konto ({numbers}). "
                    "Läuft der Worker? make logs SERVICE=worker"
                )
            time.sleep(0.5)
        detail = self.buyer_browser.api("GET", f"{STORE}/orders/{number}")
        expect_status(detail, 200, "Bestellung im Konto")
        stranger = self.customer_browser.api("GET", f"{STORE}/orders/{number}")
        expect_problem(stranger, 404, "order_not_found", "Fremde Bestellung im Konto")
        return f"{number} im Konto von {self.buyer.email}"

    def pick_list(self) -> str | None:
        number = self._order["number"]
        found = self._staff("GET", f"{ADMIN}/orders?{urllib.parse.urlencode({'q': number})}")
        expect_status(found, 200, "Bestellungen im Stellwerk")
        items = found.json()["items"]
        expect([item["number"] for item in items] == [number], f"Suche nach {number}: {items}")
        expect(items[0]["guest"] is False, "Übernommene Bestellung gilt noch als Gastbestellung")
        self._order["id"] = items[0]["id"]
        early = self._staff("POST", f"{ADMIN}/orders/{self._order['id']}/ship", {"carrier": "DHL"})
        expect_problem(early, 409, "order_not_picked", "Versand vor dem Kommissionieren")
        pick_list = self._allocated_pick_list(self._order["id"])
        piece = pick_list["items"][0]
        expect(
            (piece["state"], piece["location"]["code"]) == ("reserved", self._compartment),
            f"Pickliste: {piece}",
        )
        expect(piece["unit_code"] == self._units[0], "Nicht das älteste Stück reserviert (FIFO)")
        return f"{piece['unit_code']} in {self._compartment} reserviert"

    def pick(self) -> str | None:
        order_id = self._order["id"]
        context = {"order_id": order_id}
        wrong = self._scan("pick", self._compartment, context)
        expect(wrong["outcome"] != "applied", f"Ein Platz wurde kommissioniert: {wrong}")
        picked = self._scan("pick", self._units[0], context)
        expect(
            (picked["message"], picked["progress"]) == ("picked", {"picked": 1, "total": 1}),
            f"Kommissionieren: {picked['message']} {picked['progress']}",
        )
        self._wait_for_stock_event(
            f"{STOCK_CHANGED} für {order_id}", unit_code=self._units[0], order_id=order_id
        )
        again = self._scan("pick", self._units[0], context)
        expect(again["message"] == "already_picked", f"Zweiter Scan: {again['message']}")
        pick_list = self._staff("GET", f"{INVENTORY}/orders/{order_id}/pick-list").json()
        expect(pick_list["complete"] is True, f"Pickliste nicht vollständig: {pick_list}")
        return "1 von 1, Paket kann gepackt werden"

    def ship(self) -> str | None:
        number = self._order["number"]
        order_id = self._order["id"]
        shipped = self._staff(
            "POST",
            f"{ADMIN}/orders/{order_id}/ship",
            {"carrier": "DHL", "tracking_number": "SMOKE-0042"},
        )
        expect_status(shipped, 200, "Versenden")
        expect(
            shipped.json()["status"] == "shipped", f"Nach dem Versand: {shipped.json()['status']}"
        )
        twice = self._staff("POST", f"{ADMIN}/orders/{order_id}/ship", {})
        expect_problem(twice, 409, "invalid_order_state", "Zweiter Versand")
        message = self.mailpit.wait_for(
            self.buyer.email, f"Deine Bestellung {number} ist unterwegs"
        )
        expect("SMOKE-0042" in str(message.get("Text", "")), "Versandmail ohne Sendungsnummer")
        self._shipped_unit(self._units[0])
        line = self._stock_of(self._variant("unpainted")["id"])
        expect(line.get("in_stock") == 1, f"Bestand nach dem Versand: {line}")
        return "DHL · SMOKE-0042"

    def account_order(self) -> str | None:
        variant = self._variant("painted")
        added = self.buyer_browser.api("PUT", f"{SHOP}/cart/lines/{variant['id']}", {"quantity": 1})
        expect_status(added, 200, "Warenkorb des Kunden")
        total = added.json()["totals"]["total_cents"]
        expected = PAINTED_CENTS + SHIPPING_DE_CENTS
        expect(total == expected, f"Versand ist nie frei: Summe {total}, erwartet {expected}")
        body = {**self._guest_body(total), "save_address": True}
        del body["email"]
        placed = self._checkout(self.buyer_browser, body, str(uuid.uuid4()))
        expect_status(placed, 201, "Bestellung mit Kundenkonto")
        self._account_order = placed.json()
        expect(self._account_order["email"] == self.buyer.email, "Bestellung ohne Kontoadresse")
        book = self.buyer_browser.api("GET", f"{STORE}/addresses")
        expect_status(book, 200, "Adressbuch")
        entries = book.json()
        expect(len(entries) == 1 and entries[0]["is_default"], f"Adressbuch: {entries}")
        paid = self._pay("succeeds", str(uuid.uuid4()), token=self._account_order["public_token"])
        expect_status(paid, 200, "Zahlung der Kundenbestellung")
        self._account_order = paid.json()
        return f"{self._account_order['number']} · Adresse gespeichert"

    def backorder(self) -> str | None:
        number = self._account_order["number"]
        found = self._staff("GET", f"{ADMIN}/orders?{urllib.parse.urlencode({'q': number})}")
        order_id = found.json()["items"][0]["id"]
        pick_list = self._allocated_pick_list(order_id)
        states = [item["state"] for item in pick_list["items"]]
        expect(states == ["backordered"], f"Pickliste auf Bestellung: {states}")
        if self.stream is not None:
            self.stream.wait_for(
                lambda e: (
                    e.event == BACKORDERED and e.json().get("data", {}).get("order_id") == order_id
                ),
                what=f"{BACKORDERED} für {number}",
            )
        line = self._stock_of(self._variant("painted")["id"])
        expect(line.get("backordered") == 1, f"Fertigungsbedarf: {line}")
        return f"{number}: 1 Stück in Fertigung"

    def cancel(self) -> str | None:
        number = self._account_order["number"]
        found = self._staff("GET", f"{ADMIN}/orders?{urllib.parse.urlencode({'q': number})}")
        order_id = found.json()["items"][0]["id"]
        self._account_order["id"] = order_id
        cancelled = self._staff(
            "POST", f"{ADMIN}/orders/{order_id}/cancel", {"note": "Smoke-Test: nicht lieferbar"}
        )
        expect_status(cancelled, 200, "Stornieren")
        order = cancelled.json()
        expect(order["status"] == "cancelled", f"Nach dem Storno: {order['status']}")
        statuses = [p["status"] for p in order["payments"]]
        expect(statuses == ["refunded"], f"Zahlung nicht erstattet: {statuses}")
        message = self.mailpit.wait_for(
            self.buyer.email, f"Deine Bestellung {number} wurde storniert"
        )
        text = str(message.get("Text", ""))
        expect("erstatt" in text, "Stornomail erwähnt die Erstattung nicht")
        expect("Smoke-Test: nicht lieferbar" in text, "Stornomail ohne Hinweis")
        return f"{number} storniert, 85,80 € erstattet"

    def order_pages(self) -> str | None:
        mine = self.buyer_browser.page("/konto/bestellungen")
        expect_status(mine, 200, "/konto/bestellungen mit Sitzung")
        anonymous = self.visitor.page("/konto/bestellungen")
        expect(
            anonymous.status in {307, 308}, f"/konto/bestellungen ohne Sitzung: {anonymous.status}"
        )
        desk = self.staff_browser.page(f"/admin/bestellungen/{self._account_order['id']}")
        expect_status(desk, 200, "/admin/bestellungen/… mit Admin-Sitzung")
        for path in (
            "/admin/lager",
            "/admin/scanner",
            f"/admin/lager/plaetze/{self._compartment}",
            f"/admin/lager/einheiten/{self._units[0]}",
        ):
            expect_status(self.staff_browser.page(path), 200, f"{path} mit Admin-Sitzung")
        return None

    def archive(self) -> str | None:
        product_id = self._product["id"]
        archived = self._staff("POST", f"{ADMIN}/products/{product_id}/archive")
        expect_status(archived, 200, "Archivieren")
        gone = self.visitor.api("GET", f"{SHOP}/products/{self._product['slug']}")
        expect_problem(gone, 404, "product_not_found", "Archiviertes Produkt im Shop")
        return None

    def quick_entry(self) -> str | None:
        """The phone at the crates: a new model in red with the photo, then the same in blue."""
        path = f"{ADMIN}/catalog/quick-entries"
        name = f"{self._product_name} Kipper"
        first = self._staff(
            "POST",
            path,
            {
                "name": name,
                "category_id": self._category_id(),
                "scale_code": "H0",
                "finish_code": "painted",
                "color": "rot",
                "price_cents": QUICK_ENTRY_CENTS,
                "asset_id": self._asset["id"],
            },
        )
        expect_status(first, 200, "Schnellerfassung")
        entry = first.json()
        product = entry["product"]
        expect((entry["new_product"], entry["new_variant"]) == (True, True), f"Erfasst: {entry}")
        expect(product["status"] == "draft", f"Neues Produkt ist {product['status']}")
        red = entry["variant"]
        expect((red["color"], red["sku"][-5:]) == ("Rot", "-H0-F"), f"Variante {red}")
        tags = [(m["scale_code"], m["finish_code"], m["color"]) for m in product["media"]]
        expect(tags == [("H0", "painted", "Rot")], f"Foto markiert mit {tags}")

        second = self._staff(
            "POST",
            path,
            {
                "product_id": product["id"],
                "scale_code": "H0",
                "finish_code": "painted",
                "color": "Blau",
                "price_cents": QUICK_ENTRY_CENTS,
            },
        )
        expect_status(second, 200, "Schnellerfassung, zweite Farbe")
        blue = second.json()["variant"]
        expect(blue["sku"].endswith("-H0-F2"), f"Zweite Farbe {blue['sku']}")

        published = self._staff("POST", f"{ADMIN}/catalog/publish-ready")
        expect_status(published, 200, "Fertige Entwürfe veröffentlichen")
        ids = [p["id"] for p in published.json()["published"]]
        expect(product["id"] in ids, f"Erfasstes Modell nicht veröffentlicht: {ids}")
        shown = self.visitor.api("GET", f"{SHOP}/products/{product['slug']}")
        expect_status(shown, 200, "Erfasstes Modell im Shop")
        colors = [v["color"] for v in shown.json()["scales"][0]["variants"]]
        expect(colors == ["Blau", "Rot"], f"Farben im Shop: {colors}")
        archived = self._staff("POST", f"{ADMIN}/products/{product['id']}/archive")
        expect_status(archived, 200, "Erfasstes Modell archivieren")
        return f"{red['sku']} (Rot), {blue['sku']} (Blau) · {len(ids)} veröffentlicht"

    # eBay on the built-in test marketplace ---------------------------------------------

    def _until[T](self, what: str, probe: Callable[[], T | None]) -> T:
        """Ask ``probe`` until it answers (the worker is at work in the meantime)."""
        deadline = time.monotonic() + MAIL_TIMEOUT
        while True:
            found = probe()
            if found is not None:
                return found
            if time.monotonic() > deadline:
                raise SmokeCheckError(
                    f"{what}: nach {MAIL_TIMEOUT:.0f} s nicht da. "
                    "Läuft der Worker? make logs SERVICE=worker"
                )
            time.sleep(0.5)

    def _ebay_connect(self) -> None:
        """The owner connects eBay, chooses the shipping policy and maps the category."""
        # Only the owner connects; the test marketplace leads straight to the callback,
        # which needs no cookie (the Stellwerk's is SameSite=Strict).
        refused = self._staff("POST", f"{EBAY}/connect")
        expect_problem(refused, 403, "insufficient_role", "Mitarbeiter verbindet eBay")
        login = self.owner_browser.api(
            "POST",
            f"{ADMIN_AUTH}/session",
            {"email": self.owner_email, "password": self.owner_password},
        )
        expect_status(login, 200, "Anmeldung des Inhabers")
        connect = self.owner_browser.api("POST", f"{EBAY}/connect")
        expect_status(connect, 200, "eBay verbinden")
        callback = urllib.parse.urlsplit(connect.json()["authorize_url"])
        handoff = self.visitor.page(f"{callback.path}?{callback.query}")
        expect_status(handoff, 200, "Rücksprung von eBay")
        expect("eBay ist verbunden" in handoff.text, "Rücksprung ohne Erfolg")
        expect("ebay=verbunden" in handoff.text, "Rücksprung führt nicht ins Stellwerk")
        replayed = self.visitor.page(f"{callback.path}?{callback.query}")
        expect("abgelaufen oder unbekannt" in replayed.text, "Rücksprung zweimal verwendbar")

        settings = self.owner_browser.api(
            "PUT",
            f"{EBAY}/settings",
            {"fulfillment_policy_id": "test-ship-dhl", "price_markup_percent": EBAY_MARKUP_PERCENT},
        )
        expect_status(settings, 200, "eBay-Einstellungen")
        expect(settings.json()["blockers"] == [], f"Fahrstraße nicht frei: {settings.json()}")
        mapped = self.owner_browser.api(
            "PUT",
            f"{EBAY}/categories",
            {"items": [{"category_id": self._category_id(), "ebay_category_id": EBAY_CATEGORY}]},
        )
        expect_status(mapped, 200, "eBay-Kategorie zuordnen")

    def ebay_sale(self) -> str | None:
        status = self._staff("GET", EBAY)
        expect_status(status, 200, "eBay-Status")
        mode = status.json()["mode"]
        if mode != "test":
            self._ebay_external = ""
            return f"übersprungen (MB_EBAY_MODE={mode})"

        self._ebay_connect()

        # A model in green, offered on eBay and synced at once.
        entry = self._staff(
            "POST",
            f"{ADMIN}/catalog/quick-entries",
            {
                "name": f"{self._product_name} Sattelzug",
                "category_id": self._category_id(),
                "scale_code": "H0",
                "finish_code": "painted",
                "color": "Grün",
                "price_cents": QUICK_ENTRY_CENTS,
                "asset_id": self._asset["id"],
                # Made to order: eBay may sell it without stock (three at once).
                "allow_backorder": True,
            },
        )
        expect_status(entry, 200, "Modell für eBay erfassen")
        product = entry.json()["product"]
        self._ebay_product = product
        published = self._staff("POST", f"{ADMIN}/products/{product['id']}/publish")
        expect_status(published, 200, "Modell für eBay veröffentlichen")
        wanted = self._staff(
            "PUT", f"{EBAY}/products/{product['id']}/listings/H0", {"wanted": True}
        )
        expect_status(wanted, 200, "Auf eBay anbieten")
        synced = self._staff("POST", f"{EBAY}/listings/{wanted.json()['id']}/sync")
        expect_status(synced, 200, "Angebot abgleichen")
        listing = synced.json()
        expect(listing["status"] == "active", f"Angebot nicht online: {listing}")
        (item,) = listing["items"]
        price = (QUICK_ENTRY_CENTS * (100 + EBAY_MARKUP_PERCENT) + 50) // 100
        expect(
            item["price_cents"] == price, f"Preis auf eBay {item['price_cents']}, erwartet {price}"
        )

        # A buyer buys; the worker turns the sale into a paid order of the shop.
        sale = self._staff("POST", f"{EBAY}/test-sales", {"sku": item["sku"], "quantity": 1})
        expect_status(sale, 201, "Testkauf")
        self._ebay_external = sale.json()["external_id"]

        def imported() -> dict[str, Any] | None:
            query = urllib.parse.urlencode({"q": self._ebay_external})
            found = self._staff("GET", f"{ADMIN}/orders?{query}").json()["items"]
            mine = [o for o in found if o["channel"] == "ebay" and o["status"] == "paid"]
            return mine[0] if mine else None

        summary = self._until("Bezahlte eBay-Bestellung", imported)
        order = self._staff("GET", f"{ADMIN}/orders/{summary['id']}").json()
        expect(order["external_ref"] == self._ebay_external, f"eBay-Nummer {order['external_ref']}")
        expect(
            order["totals"]["total_cents"] == price + SHIPPING_DE_CENTS,
            f"Summe {order['totals']['total_cents']}",
        )
        self._ebay_order = order
        found = self.mailpit._get("/api/v1/search", query=f'to:"{EBAY_TEST_BUYER}"')
        expect(not found.get("messages"), "Der Shop hat dem eBay-Käufer geschrieben")
        return f"{self._ebay_external} → {order['number']} · {price / 100:.2f} € auf eBay".replace(".", ",")

    def ebay_cancel(self) -> str | None:
        if not self._ebay_external:
            return "übersprungen"
        order_id = self._ebay_order["id"]
        refused = self._staff("POST", f"{ADMIN}/orders/{order_id}/cancel", {"note": ""})
        expect_problem(refused, 409, "marketplace_order", "Storno einer eBay-Bestellung im Shop")
        cancelled = self._staff("POST", f"{EBAY}/test-sales/{self._ebay_external}/cancel")
        expect_status(cancelled, 204, "Storno durch den Käufer")

        def followed() -> dict[str, Any] | None:
            order: dict[str, Any] = self._staff("GET", f"{ADMIN}/orders/{order_id}").json()
            return order if order["status"] == "cancelled" else None

        order = self._until("Storno im Shop", followed)
        expect(order["cancel_reason"] == "by_marketplace", f"Grund {order['cancel_reason']}")

        disconnected = self.owner_browser.api("POST", f"{EBAY}/disconnect")
        expect_status(disconnected, 200, "eBay trennen")
        listings = self._staff(
            "GET", f"{EBAY}/products/{self._ebay_product['id']}/listings"
        ).json()["items"]
        expect(
            [entry["status"] for entry in listings] == ["ended"], f"Nach dem Trennen: {listings}"
        )
        archived = self._staff("POST", f"{ADMIN}/products/{self._ebay_product['id']}/archive")
        expect_status(archived, 200, "eBay-Modell archivieren")
        return f"{order['number']} storniert (by_marketplace), Angebot beendet"

    def ebay_account_deletion(self) -> str | None:
        if not self._ebay_external:
            return "übersprungen"
        setup = self._staff("GET", f"{EBAY}/account-deletion")
        expect_status(setup, 200, "Einrichtung der Löschmeldungen")
        path = urllib.parse.urlsplit(setup.json()["endpoint"]).path
        expect(path == EBAY_ACCOUNT_DELETION, f"Adresse fürs Entwicklerkonto: {path}")

        # eBay's check of the address and its notifications arrive through Caddy, without
        # a session and without the CSRF header; eBay's signature is the proof.
        checked = "ohne Prüftoken"
        if setup.json()["token_set"]:
            check = self.visitor.api("GET", f"{path}?challenge_code=smoke-{secrets.token_hex(4)}")
            expect_status(check, 200, "eBays Prüfung der Adresse")
            answer = check.json().get("challengeResponse", "")
            expect(re.fullmatch(r"[0-9a-f]{64}", answer) is not None, f"Antwort {answer!r}")
            checked = "Prüfung beantwortet"
        notification = {
            "metadata": {"topic": "MARKETPLACE_ACCOUNT_DELETION", "schemaVersion": "1.0"},
            "notification": {
                "notificationId": f"smoke-{secrets.token_hex(8)}",
                "data": {"username": "erika_testkauf", "userId": "smoke", "eiasToken": ""},
            },
        }
        forged = self.visitor.api(
            "POST",
            path,
            notification,
            client_header=False,
            headers={"X-EBAY-SIGNATURE": "eyJhbGciOiJlY2RzYSJ9"},
        )
        expect_problem(forged, 412, "signature_invalid", "Gefälschte Löschmeldung")

        closed = self._staff("POST", f"{EBAY}/test-buyer/close-account")
        expect_status(closed, 200, "Testkäufer schließt sein eBay-Konto")
        erased = closed.json()["erased_orders"]
        expect(erased >= 1, f"Keine Bestellung gelöscht: {closed.json()}")
        orders = self._staff("GET", f"{EBAY}/orders").json()["items"]
        (mine,) = [entry for entry in orders if entry["external_id"] == self._ebay_external]
        expect(mine["buyer_erased_at"] is not None, f"Käuferdaten noch da: {mine}")
        expect(mine["buyer_name"] == mine["recipient"] == "", f"Käuferdaten noch da: {mine}")
        # The shop's order is the record the retention periods require.
        order = self._staff("GET", f"{ADMIN}/orders/{self._ebay_order['id']}").json()
        expect(order["shipping_address"]["recipient"] != "", "Shop-Bestellung ohne Anschrift")
        return f"{checked}, Fälschung 412, Käuferdaten aus {erased} eBay-Bestellung(en) gelöscht"

    # Fairs, fair news and imprint ------------------------------------------------------

    def fair(self) -> str | None:
        starts = datetime.now(UTC).date() + timedelta(days=FAIR_DAYS_AHEAD)
        created = self._staff(
            "POST",
            f"{ADMIN}/fairs",
            {
                "name": f"Smoke-Messe {secrets.token_hex(3)}",
                "starts_on": starts.isoformat(),
                "ends_on": (starts + timedelta(days=1)).isoformat(),
                "venue": "Kulturhaus",
                "street": "Hauptstraße 1",
                "postal_code": "06237",
                "city": "Leuna",
                "booth": "Stand 7",
                "published": True,
            },
        )
        expect_status(created, 201, "Messe anlegen")
        self._fair = created.json()
        fair_id = self._fair["id"]
        calendar = self.visitor.api("GET", f"{SHOP}/fairs")
        expect_status(calendar, 200, "GET /store/fairs")
        upcoming = [fair["id"] for fair in calendar.json()["upcoming"]]
        expect(fair_id in upcoming, "Die neue Messe fehlt unter den kommenden")
        event = self.visitor._send(
            "GET", f"{SHOP}/fairs/{fair_id}/calendar.ics", accept="text/calendar", cookies=None
        )
        expect_status(event, 200, "Kalenderdatei der Messe")
        expect(
            event.headers.get("content-type", "").startswith("text/calendar"),
            f"Kalenderdatei als {event.headers.get('content-type')}",
        )
        for line in (f"UID:fair-{fair_id}@", f"DTSTART;VALUE=DATE:{starts:%Y%m%d}", "END:VEVENT"):
            expect(line in event.text, f"Kalenderdatei ohne {line!r}")
        page = self.visitor.page("/termine")
        expect_status(page, 200, "GET /termine")
        expect(self._fair["name"] in page.text, "Die Messe fehlt auf /termine")
        return f"{self._fair['name']} · {self._fair['when']}"

    def fair_news(self) -> str | None:
        asked = self.visitor.api(
            "POST", f"{SHOP}/fair-news/subscriptions", {"email": self.fan, "consent": True}
        )
        expect_status(asked, 202, "Messe-Post bestellen")
        message = self.mailpit.wait_for(self.fan, "Bitte bestätige die Messe-Post", prefix=True)
        token = token_link(message, self.base_url, "/termine/bestaetigen")
        page = self.visitor.page(f"/termine/bestaetigen?token={token}")
        expect_status(page, 200, "Bestätigungsseite")
        confirmed = self.visitor.api("POST", f"{SHOP}/fair-news/confirmations", {"token": token})
        expect_status(confirmed, 204, "Messe-Post bestätigen")
        again = self.visitor.api("POST", f"{SHOP}/fair-news/confirmations", {"token": token})
        expect_problem(again, 400, "fair_news_token_invalid", "Derselbe Link ein zweites Mal")
        counts = self._staff("GET", f"{ADMIN}/fair-news")
        expect_status(counts, 200, "Zähler der Messe-Post")
        expect(counts.json()["confirmed"] >= 1, f"Keine Bestätigten: {counts.text}")
        return self.fan

    def announce(self) -> str | None:
        fair_id = self._fair["id"]
        announced = self._staff("POST", f"{ADMIN}/fairs/{fair_id}/announcement")
        expect_status(announced, 202, "Messe ankündigen")
        recipients = announced.json()["recipients"]
        expect(recipients >= 1, f"Ankündigung an {recipients} Empfänger")
        again = self._staff("POST", f"{ADMIN}/fairs/{fair_id}/announcement")
        expect_problem(again, 409, "fair_already_announced", "Zweite Ankündigung")
        message = self.mailpit.wait_for(
            self.fan, f"Wir stellen aus: {self._fair['name']}", prefix=True
        )
        text = str(message.get("Text", ""))
        expect(f"{SHOP}/fairs/{fair_id}/calendar.ics" in text, "Ankündigung ohne Kalenderlink")
        expect("Stand 7" in text, "Ankündigung ohne Stand")
        self._leave_token = token_link(message, self.base_url, "/termine/abmelden")
        if self.stream is not None:
            self.stream.wait_for(
                lambda e: (
                    e.event == FAIR_ANNOUNCED and e.json().get("data", {}).get("fair_id") == fair_id
                ),
                what=f"{FAIR_ANNOUNCED} für {fair_id}",
            )
        return f"an {recipients} Empfänger"

    def fair_news_leave(self) -> str | None:
        left = self.visitor.api(
            "POST", f"{SHOP}/fair-news/unsubscriptions", {"token": self._leave_token}
        )
        expect_status(left, 204, "Abmelden")
        removed = self._staff("DELETE", f"{ADMIN}/fairs/{self._fair['id']}")
        expect_status(removed, 204, "Messe löschen")
        gone = self.visitor.api("GET", f"{SHOP}/fairs/{self._fair['id']}/calendar.ics")
        expect_problem(gone, 404, "fair_not_found", "Kalenderdatei einer gelöschten Messe")
        return None

    def imprint(self) -> str | None:
        response = self.visitor.api("GET", f"{SHOP}/imprint")
        expect_status(response, 200, "GET /store/imprint")
        imprint = response.json()
        expect(
            imprint["complete"] is True,
            f"Impressum unvollständig (MB_IMPRINT_* in .env): {imprint}",
        )
        page = self.visitor.page("/impressum")
        expect_status(page, 200, "GET /impressum")
        expect(imprint["street"] in page.text, "Die Anschrift fehlt auf /impressum")
        countries = self.visitor.api("GET", f"{SHOP}/cart").json()["countries"]
        expect(len(countries) == EU_MEMBER_STATES, f"{len(countries)} Lieferländer statt 27")
        rates = {country["code"]: country["rate_cents"] for country in countries}
        expect(rates.get("DE") == SHIPPING_DE_CENTS, f"Versand DE: {rates.get('DE')}")
        expect(rates.get("AT") == SHIPPING_EU_CENTS, f"Versand AT: {rates.get('AT')}")
        expect(
            all(country["free_from_cents"] is None for country in countries),
            "Versandkostenfrei sollte es nirgends geben",
        )
        return f"{imprint['company']}, {imprint['city']} · {len(countries)} Lieferländer"

    def making_of(self) -> str | None:
        page = self.visitor.page("/so-entsteht-ein-modell")
        expect_status(page, 200, "GET /so-entsteht-ein-modell")
        for text in ("So entsteht ein Modell", "Stückliste", "Fahrgestellrahmen", "Zerlegt"):
            expect(text in page.text, f"„{text}“ fehlt auf /so-entsteht-ein-modell")
        start = self.visitor.page("/")
        expect('href="/so-entsteht-ein-modell"' in start.text, "Die Startseite führt nicht zur Zeichnung")
        return "Seite mit Stückliste, von der Startseite verlinkt"

    def customer_on_admin(self) -> str | None:
        session = self.customer_browser.cookies[CUSTOMER_COOKIE]
        as_is = self.customer_browser.api("GET", f"{ADMIN_AUTH}/me")
        expect_problem(as_is, 401, "not_authenticated", "Admin-/me mit Kunden-Cookie")
        # The shop session token under the admin cookie's name must not open the admin area.
        forged = {STAFF_COOKIE: session}
        renamed = self.visitor.api("GET", f"{ADMIN_AUTH}/me", cookies=forged)
        expect_problem(renamed, 401, "not_authenticated", "Admin-/me mit Kunden-Token als mb_admin")
        stream = self.visitor.api("GET", ADMIN_EVENTS, cookies=forged)
        expect_problem(stream, 401, "not_authenticated", "Ereignisstrom mit Kunden-Token")
        return None

    def staff_on_store(self) -> str | None:
        session = self.staff_browser.cookies[STAFF_COOKIE]
        response = self.visitor.api("GET", f"{STORE}/me", cookies={CUSTOMER_COOKIE: session})
        expect_problem(response, 401, "not_authenticated", "Shop-/me mit Admin-Token")
        return None

    def csrf(self) -> str | None:
        login = self.visitor.api(
            "POST",
            f"{STORE}/session",
            {"email": self.customer.email, "password": self.customer.password},
            client_header=False,
        )
        expect_problem(login, 403, "csrf_header_missing", "Anmeldung ohne Header")
        expect(login.set_cookie(CUSTOMER_COOKIE) is None, "Anmeldung ohne Header setzt Cookie")
        logout = self.customer_browser.api("DELETE", f"{STORE}/session", client_header=False)
        expect_problem(logout, 403, "csrf_header_missing", "Abmelden ohne Header")
        still = self.customer_browser.api("GET", f"{STORE}/me")
        expect_status(still, 200, "Sitzung nach abgelehntem Abmelden")
        return None

    def staff_logout(self) -> str | None:
        response = self.staff_browser.api("DELETE", f"{ADMIN_AUTH}/session")
        expect_status(response, 204, "Admin-Abmeldung")
        expect(STAFF_COOKIE not in self.staff_browser.cookies, "mb_admin wurde nicht gelöscht")
        expect_problem(
            self.staff_browser.api("GET", f"{ADMIN_AUTH}/me"),
            401,
            "not_authenticated",
            "Admin-/me nach dem Abmelden",
        )
        return None

    def delete_account(self) -> str | None:
        response = self.customer_browser.api(
            "POST", f"{STORE}/me/delete", {"password": self.customer.password}
        )
        expect_status(response, 204, "Konto löschen")
        expect(CUSTOMER_COOKIE not in self.customer_browser.cookies, "mb_session nicht gelöscht")
        login = self._login(self.customer.password)
        expect_problem(login, 401, "invalid_credentials", "Anmeldung nach dem Löschen")
        return None


def _account_of(event: ServerSentEvent) -> object:
    return event.json().get("data", {}).get("account_id")


def run(steps: Iterable[tuple[str, Callable[[], str | None]]]) -> int:
    steps = list(steps)
    for number, (title, check) in enumerate(steps, start=1):
        try:
            detail = check()
        except SmokeCheckError as failure:
            print(f"✗ {title}\n    {failure}", flush=True)
            print(f"\nFehlgeschlagen bei Schritt {number} von {len(steps)}.")
            return 1
        except Exception:  # a bug here, or a very odd answer
            print(f"✗ {title}\n    Unerwarteter Fehler:", flush=True)
            traceback.print_exc()
            print(f"\nFehlgeschlagen bei Schritt {number} von {len(steps)}.")
            return 1
        print(f"✓ {title}" + (f" · {detail}" if detail else ""), flush=True)
    print(f"\nAlle {len(steps)} Schritte erfolgreich.")
    return 0


def parse_settings(argv: list[str]) -> Settings:
    parser = argparse.ArgumentParser(
        description="End-to-End-Smoke-Test des laufenden Stacks (make smoke)."
    )
    parser.add_argument("--base-url", default=os.environ.get("SMOKE_BASE_URL", "https://localhost"))
    parser.add_argument(
        "--mailpit-url", default=os.environ.get("SMOKE_MAILPIT_URL", "http://localhost:8025")
    )
    parser.add_argument(
        "--ca-file",
        help="Root-Zertifikat von Caddys interner CA (make smoke holt es aus dem Container)",
    )
    args = parser.parse_args(argv)
    # Only these schemes are ever opened (urllib would also open file: URLs).
    if urllib.parse.urlsplit(args.base_url).scheme != "https":
        parser.error("--base-url muss mit https:// beginnen (der Stack läuft hinter Caddy)")
    if urllib.parse.urlsplit(args.mailpit_url).scheme not in {"http", "https"}:
        parser.error("--mailpit-url muss mit http:// oder https:// beginnen")
    staff_email = os.environ.get("SMOKE_STAFF_EMAIL", "")
    staff_password = os.environ.get("SMOKE_STAFF_PASSWORD", "")
    owner_email = os.environ.get("SMOKE_OWNER_EMAIL", "")
    owner_password = os.environ.get("SMOKE_OWNER_PASSWORD", "")
    if not (staff_email and staff_password and owner_email and owner_password):
        parser.error(
            "SMOKE_STAFF_EMAIL, SMOKE_STAFF_PASSWORD, SMOKE_OWNER_EMAIL und "
            "SMOKE_OWNER_PASSWORD müssen gesetzt sein (make smoke)"
        )
    return Settings(
        base_url=args.base_url.rstrip("/"),
        mailpit_url=args.mailpit_url.rstrip("/"),
        staff_email=staff_email,
        staff_password=staff_password,
        owner_email=owner_email,
        owner_password=owner_password,
        ca_file=args.ca_file,
    )


def main(argv: list[str]) -> int:
    settings = parse_settings(argv)
    print(f"Smoke-Test gegen {settings.base_url} (Mails: {settings.mailpit_url})\n", flush=True)
    try:
        demo = Demo(settings)
    except SmokeCheckError as failure:
        print(f"✗ {failure}")
        return 1
    return run(demo.steps())


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
