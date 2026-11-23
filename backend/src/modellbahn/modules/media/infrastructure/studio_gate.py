"""When the photo studio may work: one photo at a time, and only with memory to spare.

A cut-out takes about 1.3 GB for a few seconds. On a small server that is most of what
is free, and a host without memory does not slow down, it stops answering. So the gate
keeps the studio waiting

* for a while after the worker started (a roll-out builds images and starts every
  service at that moment),
* for a pause after each photo, so other events get their turn and memory is returned,
* and as long as the host has less free memory than a photo needs with a margin, but
  not for ever: a photo that has waited ``max_wait`` goes through anyway. A host that
  never has the margin (other services keep it busy) would otherwise hold every photo
  in "being processed" for good; the worker's memory limit keeps a shortfall to the
  worker, and a run that is killed is not started a third time (``MAX_STUDIO_TRIES``).
"""

import time
from collections.abc import Callable
from datetime import timedelta
from pathlib import Path
from typing import Final

MEMINFO: Final = Path("/proc/meminfo")
# How long a photo waits before memory is looked at again.
MEMORY_RETRY: Final = timedelta(seconds=30)


def available_memory_mb(meminfo: Path = MEMINFO) -> int | None:
    """What the host can still hand out, in MB; ``None`` where the kernel does not say.

    Inside a container ``/proc/meminfo`` shows the host, which is what matters here.
    """
    try:
        for line in meminfo.read_text(encoding="ascii").splitlines():
            if line.startswith("MemAvailable:"):
                return int(line.split()[1]) // 1024
    except (OSError, ValueError, IndexError):
        return None
    return None


class MemoryStudioGate:
    """The gate described above. Used from the worker's single event loop."""

    def __init__(
        self,
        *,
        min_free_mb: int,
        warmup: timedelta,
        pause: timedelta,
        max_wait: timedelta = timedelta(minutes=20),
        available_mb: Callable[[], int | None] = available_memory_mb,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._min_free_mb = min_free_mb
        self._pause = pause.total_seconds()
        self._max_wait = max_wait
        self._available_mb = available_mb
        self._monotonic = monotonic
        self._free_from = monotonic() + warmup.total_seconds()

    def wait(self, *, waited: timedelta = timedelta(0)) -> tuple[timedelta, str] | None:
        remaining = self._free_from - self._monotonic()
        if remaining > 0:
            return timedelta(seconds=remaining), "the photo studio pauses between photos"
        if waited >= self._max_wait:
            return None
        available = self._available_mb()
        if available is not None and available < self._min_free_mb:
            return (
                MEMORY_RETRY,
                f"the photo studio waits for memory: {available} MB free, "
                f"{self._min_free_mb} MB needed",
            )
        return None

    def done(self) -> None:
        self._free_from = self._monotonic() + self._pause
