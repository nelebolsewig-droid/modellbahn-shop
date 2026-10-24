"""Periodic jobs of the worker: they run, survive failures and stop on request."""

import asyncio
from datetime import timedelta

from modellbahn.platform.periodic import PeriodicJob, run_periodically


async def test_runs_again_after_a_failure_and_stops() -> None:
    stop = asyncio.Event()
    runs: list[int] = []

    async def job() -> None:
        runs.append(len(runs))
        if len(runs) == 1:
            msg = "database restarting"
            raise ConnectionError(msg)
        if len(runs) == 3:
            stop.set()

    periodic = PeriodicJob(name="test.job", interval=timedelta(milliseconds=10), run=job)
    async with asyncio.timeout(2):
        await run_periodically(periodic, stop)
    assert runs == [0, 1, 2]


async def test_a_set_stop_ends_the_wait_at_once() -> None:
    stop = asyncio.Event()
    calls = 0

    async def job() -> None:
        nonlocal calls
        calls += 1
        stop.set()

    periodic = PeriodicJob(name="test.job", interval=timedelta(hours=1), run=job)
    async with asyncio.timeout(1):
        await run_periodically(periodic, stop)
    assert calls == 1
