"""Structured logging and the per-request context (request id, access log, crash guard)."""

import logging
import re
import time
from typing import Final

import structlog
from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from modellbahn.platform.config import Environment
from modellbahn.platform.db import is_database_unavailable
from modellbahn.platform.errors import database_unavailable_response, internal_error_response
from modellbahn.platform.ids import new_id

REQUEST_ID_HEADER: Final = "X-Request-ID"
_VALID_REQUEST_ID: Final = re.compile(r"^[A-Za-z0-9._-]{1,128}$")
# Probes hit these every few seconds; logging them at INFO would drown the rest.
_QUIET_PATHS: Final = frozenset({"/healthz", "/readyz"})

_access_logger = structlog.get_logger("modellbahn.access")


def configure_logging(*, environment: Environment, level: str) -> None:
    """Route structlog and stdlib logging (uvicorn, SQLAlchemy) through one formatter.

    Production writes one JSON object per line; development and tests get the
    human-readable console renderer. Neither renders the local variables of a
    traceback.
    """
    shared: list[structlog.typing.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
    ]
    # Tracebacks never show local variables: they would put passwords, session tokens
    # and connection parameters into the logs. structlog renders them by default.
    final: list[structlog.typing.Processor]
    if environment is Environment.PRODUCTION:
        final = [
            structlog.processors.ExceptionRenderer(
                structlog.tracebacks.ExceptionDictTransformer(show_locals=False)
            ),
            structlog.processors.JSONRenderer(),
        ]
    else:
        # The plain formatter rather than rich's: it is fast, which matters because
        # logging runs on the event loop.
        final = [
            structlog.dev.ConsoleRenderer(
                colors=False, exception_formatter=structlog.dev.plain_traceback
            )
        ]

    structlog.configure(
        processors=[*shared, structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared,
        processors=[structlog.stdlib.ProcessorFormatter.remove_processors_meta, *final],
    )
    handler = logging.StreamHandler()
    handler.setFormatter(formatter)
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)
    # uvicorn installs its own handlers; let its records reach ours instead.
    for name in ("uvicorn", "uvicorn.error"):
        uvicorn_logger = logging.getLogger(name)
        uvicorn_logger.handlers = []
        uvicorn_logger.propagate = True
    # RequestContextMiddleware writes the access log (with the request id) itself.
    access_logger = logging.getLogger("uvicorn.access")
    access_logger.handlers = []
    access_logger.propagate = False


class RequestContextMiddleware:
    """Pure ASGI middleware that gives every HTTP request an id and an access log line.

    The id is taken from a well-formed incoming ``X-Request-ID`` (set by a proxy)
    or generated, bound to the structlog context and echoed in the response.
    Exceptions nobody handled are logged with that id and answered with a generic
    500 problem, so no internals leak to the client. An unreachable database is
    answered with 503 ``database_unavailable`` and logged without a traceback.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = _incoming_request_id(scope) or new_id().hex
        started = time.perf_counter()
        status_code = 500
        response_started = False

        async def send_with_request_id(message: Message) -> None:
            nonlocal status_code, response_started
            if message["type"] == "http.response.start":
                response_started = True
                status_code = message["status"]
                MutableHeaders(scope=message)[REQUEST_ID_HEADER] = request_id
            await send(message)

        with structlog.contextvars.bound_contextvars(request_id=request_id):
            try:
                await self.app(scope, receive, send_with_request_id)
            except Exception as exc:
                if response_started:
                    _access_logger.exception(
                        "request.failed", method=scope["method"], path=scope["path"]
                    )
                    raise
                if is_database_unavailable(exc):
                    # An outage, not a bug: no traceback, and the client may try again.
                    _access_logger.warning(
                        "request.database_unavailable",
                        method=scope["method"],
                        path=scope["path"],
                        error=f"{type(exc).__name__}: {exc}",
                    )
                    response = database_unavailable_response()
                else:
                    _access_logger.exception(
                        "request.failed", method=scope["method"], path=scope["path"]
                    )
                    response = internal_error_response()
                response.headers[REQUEST_ID_HEADER] = request_id
                await response(scope, receive, send)
                status_code = response.status_code
            finally:
                duration_ms = round((time.perf_counter() - started) * 1000, 1)
                log = _access_logger.debug if scope["path"] in _QUIET_PATHS else _access_logger.info
                log(
                    "request.completed",
                    method=scope["method"],
                    path=scope["path"],
                    status=status_code,
                    duration_ms=duration_ms,
                )


def _incoming_request_id(scope: Scope) -> str | None:
    for name, value in scope["headers"]:
        if name == b"x-request-id":
            candidate = value.decode("latin-1")
            return candidate if _VALID_REQUEST_ID.match(candidate) else None
    return None
