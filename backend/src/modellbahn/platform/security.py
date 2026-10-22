"""Security primitives: password hashing, opaque tokens, CSRF header guard."""

import asyncio
import hashlib
import secrets
from email.message import Message
from typing import Final, Self

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import Request

from modellbahn.platform.config import Settings
from modellbahn.platform.errors import ForbiddenError, UnsupportedMediaTypeError

CSRF_HEADER: Final = "X-Modellbahn-Client"
CSRF_HEADER_VALUE: Final = "web"
UNSAFE_METHODS: Final = frozenset({"POST", "PUT", "PATCH", "DELETE"})
TOKEN_BYTES: Final = 32


class Argon2PasswordHasher:
    """Argon2id password hashing.

    Hashing is CPU- and memory-bound and would block the event loop, so the async
    methods run it in a worker thread (argon2-cffi releases the GIL).
    """

    def __init__(self, *, time_cost: int, memory_cost: int, parallelism: int) -> None:
        self._hasher = PasswordHasher(
            time_cost=time_cost, memory_cost=memory_cost, parallelism=parallelism
        )
        # Verifying against this hash makes a login for an unknown address take as
        # long as one for a known address.
        self._dummy_hash = self._hasher.hash(secrets.token_urlsafe(TOKEN_BYTES))

    @classmethod
    def from_settings(cls, settings: Settings) -> Self:
        """A hasher with the Argon2 parameters configured in ``settings``."""
        return cls(
            time_cost=settings.argon2_time_cost,
            memory_cost=settings.argon2_memory_cost,
            parallelism=settings.argon2_parallelism,
        )

    async def hash(self, password: str) -> str:
        """Hash ``password`` with a fresh salt."""
        return await asyncio.to_thread(self._hasher.hash, password)

    async def verify(self, password_hash: str, password: str) -> bool:
        """True if ``password`` matches; False for a wrong password or an unusable hash."""
        return await asyncio.to_thread(self._verify, password_hash, password)

    async def dummy_verify(self, password: str) -> None:
        """Spend the time of a real verification without checking anything."""
        await asyncio.to_thread(self._verify, self._dummy_hash, password)

    def needs_rehash(self, password_hash: str) -> bool:
        """True if the hash was made with other parameters than the current ones."""
        try:
            return self._hasher.check_needs_rehash(password_hash)
        except InvalidHashError:
            return False

    def _verify(self, password_hash: str, password: str) -> bool:
        try:
            return self._hasher.verify(password_hash, password)
        except (VerificationError, InvalidHashError):
            return False


def generate_token() -> str:
    """A new opaque token (32 random bytes, URL-safe Base64)."""
    return secrets.token_urlsafe(TOKEN_BYTES)


def hash_token(token: str) -> str:
    """SHA-256 hex digest of a token; only this form is ever stored.

    Tokens carry 256 bits of entropy, so a fast unsalted hash is sufficient: the
    point is that a database leak does not reveal usable tokens.
    """
    return hashlib.sha256(token.encode()).hexdigest()


async def csrf_guard(request: Request) -> None:
    """Reject state-changing API requests that a foreign site could have forged.

    Browsers only send custom headers cross-origin after a CORS preflight, which
    this API never approves; requiring ``X-Modellbahn-Client: web`` therefore
    proves the request came from our own frontend. Bodies must be JSON, because
    ``text/plain`` and form bodies are what cross-site forms can send.
    """
    if request.method not in UNSAFE_METHODS or not request.url.path.startswith("/api/"):
        return
    if request.headers.get(CSRF_HEADER) != CSRF_HEADER_VALUE:
        raise ForbiddenError(
            f"State-changing requests must send the header '{CSRF_HEADER}: {CSRF_HEADER_VALUE}'.",
            code="csrf_header_missing",
        )
    if _has_body(request) and not _is_json(request.headers.get("content-type")):
        raise UnsupportedMediaTypeError("Request bodies must be sent as application/json.")


def _has_body(request: Request) -> bool:
    content_length = request.headers.get("content-length")
    if content_length is not None:
        return content_length.strip() != "0"
    return "transfer-encoding" in request.headers


def _is_json(content_type: str | None) -> bool:
    if not content_type:
        return False
    message = Message()
    message["content-type"] = content_type
    subtype = message.get_content_subtype()
    return message.get_content_maintype() == "application" and (
        subtype == "json" or subtype.endswith("+json")
    )
