#!/usr/bin/env python3
"""End-to-end smoke test of the running stack: ``make smoke`` (after ``make up``).

Drives the demo of step 2 through Caddy the way the browser does: start page,
registration, verification mail in Mailpit, verification with login, logout, password
reset, staff login and the live event stream of the "Stellwerk" - plus the boundaries
that keep it safe: shop and admin sessions do not mix, and state-changing requests
without the CSRF header are refused.

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
import ipaddress
import json
import os
import queue
import re
import secrets
import ssl
import sys
import threading
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request
import uuid
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from email.message import Message
from http import HTTPStatus
from http.cookies import Morsel, SimpleCookie
from typing import IO, Any, Final

API: Final = "/api/v1"
STORE: Final = f"{API}/store/account"
ADMIN_AUTH: Final = f"{API}/admin/auth"
ADMIN_EVENTS: Final = f"{API}/admin/events"

CLIENT_HEADER: Final = "X-Modellbahn-Client"
CUSTOMER_COOKIE: Final = "mb_session"
STAFF_COOKIE: Final = "mb_admin"

REGISTERED: Final = "identity.customer.registered"
EMAIL_VERIFIED: Final = "identity.account.email_verified"

HTTP_TIMEOUT: Final = 15.0
MAIL_TIMEOUT: Final = 30.0
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
    ) -> Response:
        headers: dict[str, str] = {}
        if client_header and method in {"POST", "PUT", "PATCH", "DELETE"}:
            headers[CLIENT_HEADER] = "web"
        return self._send(
            method, path, accept=JSON_ACCEPT, body=body, headers=headers, cookies=cookies
        )

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

    def wait_for(self, recipient: str, subject: str) -> dict[str, Any]:
        """The full message to ``recipient`` with ``subject``, once it has arrived."""
        deadline = time.monotonic() + MAIL_TIMEOUT
        while True:
            found = self._get("/api/v1/search", query=f'to:"{recipient}"', limit="50")
            for summary in found.get("messages") or []:
                if summary.get("Subject") == subject:
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
    ca_file: str | None


class Demo:
    """The steps of the demo, in order. Each returns an optional detail for the log."""

    def __init__(self, settings: Settings) -> None:
        opener = build_opener(tls_context(settings.base_url, settings.ca_file))
        self.base_url = settings.base_url
        self.staff_email = settings.staff_email
        self.staff_password = settings.staff_password
        self.visitor = Browser(settings.base_url, opener)
        self.customer_browser = Browser(settings.base_url, opener)
        self.staff_browser = Browser(settings.base_url, opener)
        self.mailpit = Mailpit(settings.mailpit_url, opener)
        tag = _unique("smoke")
        self.customer = Customer(email=f"{tag}@example.com", display_name=f"Smoke {tag[-10:]}")
        self.live_customer = Customer(
            email=f"{tag}-live@example.com", display_name=f"Live {tag[-10:]}"
        )
        self.started_at = time.time()
        self.stream: EventStream | None = None
        # Handed from one step to the next.
        self._verify_token = ""
        self._reset_token = ""
        self._old_password = ""

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
        expect("Hier entsteht" in response.text, "Startseite ohne „Hier entsteht …“")
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
    if not staff_email or not staff_password:
        parser.error("SMOKE_STAFF_EMAIL und SMOKE_STAFF_PASSWORD müssen gesetzt sein (make smoke)")
    return Settings(
        base_url=args.base_url.rstrip("/"),
        mailpit_url=args.mailpit_url.rstrip("/"),
        staff_email=staff_email,
        staff_password=staff_password,
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
