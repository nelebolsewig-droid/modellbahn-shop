"""Reacting to the exit signal before uvicorn's graceful shutdown waits for open streams."""

import asyncio
import signal
from types import FrameType

from modellbahn.platform.lifecycle import on_exit_signal


async def test_runs_the_callback_and_still_calls_the_previous_handler() -> None:
    callbacks: list[str] = []
    previous_calls: list[int] = []

    def previous(signum: int, frame: FrameType | None) -> None:
        previous_calls.append(signum)

    original = signal.signal(signal.SIGUSR1, previous)
    try:
        with on_exit_signal(lambda: callbacks.append("streams closed"), signals=[signal.SIGUSR1]):
            signal.raise_signal(signal.SIGUSR1)
            # The callback runs on the event loop, not inside the signal handler.
            await asyncio.sleep(0)
            assert callbacks == ["streams closed"]
            assert previous_calls == [signal.SIGUSR1]
        # Leaving the context puts the previous handler back.
        assert signal.getsignal(signal.SIGUSR1) is previous
    finally:
        signal.signal(signal.SIGUSR1, original)


def test_does_nothing_outside_the_main_thread() -> None:
    def install() -> object:
        with on_exit_signal(lambda: None, signals=[signal.SIGUSR1]):
            return signal.getsignal(signal.SIGUSR1)

    async def in_a_thread() -> object:
        return await asyncio.to_thread(install)

    before = signal.getsignal(signal.SIGUSR1)
    assert asyncio.run(in_a_thread()) is before
