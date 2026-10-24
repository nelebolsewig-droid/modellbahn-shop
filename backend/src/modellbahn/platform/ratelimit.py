"""Per-client limits for requests that attackers like to repeat: logins, registrations, resets.

The account lockout protects one account; it does nothing against trying one
password on many addresses, or against a script that sends registrations and
reset requests in bulk. This brake counts requests per client address.
"""

import math
import time
from collections import deque
from collections.abc import Awaitable, Callable
from typing import Final

from fastapi import Request

from modellbahn.platform.errors import TooManyRequestsError
from modellbahn.platform.http import app_state

# Expired entries are swept out every this many requests, which bounds memory.
_SWEEP_EVERY: Final = 1024


class RateLimiter:
    """At most ``limit`` requests per key within a sliding window of ``window_seconds``.

    The counters live in the memory of one process. With several API processes,
    each counts on its own and the effective limit multiplies, which is still a
    brake against scripted guessing; a shared store becomes necessary only then.
    A ``limit`` of 0 switches the limiter off.
    """

    def __init__(
        self,
        *,
        limit: int,
        window_seconds: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._limit = limit
        self._window = window_seconds
        self._clock = clock
        self._hits: dict[str, deque[float]] = {}
        self._calls = 0

    @property
    def enabled(self) -> bool:
        return self._limit > 0

    def hit(self, key: str) -> float | None:
        """Count a request for ``key``; return seconds to wait if it exceeds the limit.

        A rejected request is not counted, so a client that waits as told gets through.
        """
        if not self.enabled:
            return None
        now = self._clock()
        self._calls += 1
        if self._calls % _SWEEP_EVERY == 0:
            self._sweep(now)
        hits = self._hits.setdefault(key, deque())
        while hits and now - hits[0] >= self._window:
            hits.popleft()
        if len(hits) >= self._limit:
            return self._window - (now - hits[0])
        hits.append(now)
        return None

    def _sweep(self, now: float) -> None:
        expired = [
            key for key, hits in self._hits.items() if not hits or now - hits[-1] >= self._window
        ]
        for key in expired:
            del self._hits[key]


def rate_limit(state_name: str) -> Callable[[Request], Awaitable[None]]:
    """A route dependency that answers 429 ``too_many_requests`` beyond a limiter's limit.

    The limiter is the one the composition root put on ``app.state.<state_name>``, so
    that routers defined at import time share the instance of the running app. The
    client address comes from the connection, which behind the reverse proxy is the
    address the proxy reported (uvicorn's ``--forwarded-allow-ips``).
    """

    async def check(request: Request) -> None:
        limiter = app_state(request, state_name, RateLimiter)
        client = request.client.host if request.client else "unknown"
        wait = limiter.hit(client)
        if wait is not None:
            raise TooManyRequestsError(
                "Too many requests of this kind. Please wait before trying again.",
                headers={"Retry-After": str(max(1, math.ceil(wait)))},
            )

    return check
