"""Jobs the worker runs at a fixed interval, next to the outbox dispatcher."""

import asyncio
import contextlib
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import timedelta

import structlog

_logger = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class PeriodicJob:
    """Housekeeping such as removing abandoned uploads. Must be safe to run at any time."""

    name: str
    interval: timedelta
    run: Callable[[], Awaitable[object]]


async def run_periodically(job: PeriodicJob, stop: asyncio.Event) -> None:
    """Run ``job`` now and then every ``interval`` until ``stop`` is set.

    A failing run is logged and does not end the loop: the next run tries again, as
    after a short database outage. Several workers may run the same job side by side,
    so a job must tolerate that (for example by locking rows with SKIP LOCKED).
    """
    while not stop.is_set():
        try:
            await job.run()
        except Exception:
            _logger.exception("periodic.job_failed", job=job.name)
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), timeout=job.interval.total_seconds())
