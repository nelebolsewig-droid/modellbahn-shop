"""Hooks into the life of the server process."""

import asyncio
import contextlib
import signal
import threading
from collections.abc import Callable, Iterator, Sequence
from types import FrameType
from typing import Final

EXIT_SIGNALS: Final = (signal.SIGTERM, signal.SIGINT)


@contextlib.contextmanager
def on_exit_signal(
    callback: Callable[[], None], *, signals: Sequence[signal.Signals] = EXIT_SIGNALS
) -> Iterator[None]:
    """Run ``callback`` on the event loop as soon as an exit signal arrives.

    Uvicorn answers SIGTERM by refusing new connections and waiting (up to
    ``--timeout-graceful-shutdown``) for the open ones to finish; only then does it
    run the lifespan shutdown. Responses that never finish on their own, like
    Server-Sent Event streams, need to learn about the signal earlier. The handler
    installed here passes the signal on to the one installed before (uvicorn's),
    which still does the actual shutdown, and the previous handlers are restored
    when the context ends. Signals can only be handled in the main thread;
    elsewhere this does nothing.
    """
    if threading.current_thread() is not threading.main_thread():
        yield
        return
    loop = asyncio.get_running_loop()
    previous = {signum: signal.getsignal(signum) for signum in signals}

    def handle(signum: int, frame: FrameType | None) -> None:
        loop.call_soon_threadsafe(callback)
        chained = previous[signal.Signals(signum)]
        if callable(chained):
            chained(signum, frame)
        elif chained == signal.SIG_DFL:
            # Nobody handled the signal before: let it have its default effect.
            signal.signal(signum, signal.SIG_DFL)
            signal.raise_signal(signum)

    for signum in signals:
        signal.signal(signum, handle)
    try:
        yield
    finally:
        for signum, handler in previous.items():
            # None means a handler not installed from Python, which cannot be restored.
            if handler is not None:
                signal.signal(signum, handler)
