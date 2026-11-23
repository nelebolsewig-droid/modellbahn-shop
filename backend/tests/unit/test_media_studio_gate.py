"""The photo studio's gate: one photo at a time, only with memory to spare."""

from datetime import timedelta
from pathlib import Path

from modellbahn.modules.media.infrastructure.studio_gate import (
    MEMORY_RETRY,
    MemoryStudioGate,
    available_memory_mb,
)


class Host:
    """A clock and a memory gauge to turn by hand."""

    def __init__(self, free_mb: int | None = 3000) -> None:
        self.now = 1000.0
        self.free_mb = free_mb

    def gate(self, *, warmup: float = 300, pause: float = 20) -> MemoryStudioGate:
        return MemoryStudioGate(
            min_free_mb=1800,
            warmup=timedelta(seconds=warmup),
            pause=timedelta(seconds=pause),
            available_mb=lambda: self.free_mb,
            monotonic=lambda: self.now,
        )


def test_waits_after_the_start_of_the_worker() -> None:
    host = Host()
    gate = host.gate()
    wait = gate.wait()
    assert wait is not None
    assert wait[0] == timedelta(seconds=300)
    host.now += 299
    assert gate.wait() is not None
    host.now += 1
    assert gate.wait() is None


def test_pauses_after_each_photo() -> None:
    host = Host()
    gate = host.gate(warmup=0)
    assert gate.wait() is None
    gate.done()
    wait = gate.wait()
    assert wait is not None
    assert wait[0] == timedelta(seconds=20)
    host.now += 20
    assert gate.wait() is None


def test_waits_while_memory_is_short() -> None:
    host = Host(free_mb=900)
    gate = host.gate(warmup=0)
    wait = gate.wait()
    assert wait is not None
    assert wait[0] == MEMORY_RETRY
    assert "900 MB free" in wait[1]
    host.free_mb = 1800
    assert gate.wait() is None


def test_a_photo_that_waited_long_enough_goes_ahead_without_the_memory() -> None:
    host = Host(free_mb=600)
    gate = host.gate(warmup=0)
    assert gate.wait(waited=timedelta(minutes=19)) is not None
    assert gate.wait(waited=timedelta(minutes=20)) is None
    # The pause between photos still holds.
    gate.done()
    assert gate.wait(waited=timedelta(hours=1)) is not None


def test_goes_ahead_where_the_host_does_not_tell_its_memory() -> None:
    assert Host(free_mb=None).gate(warmup=0).wait() is None


def test_reads_the_kernels_estimate_of_what_is_available(tmp_path: Path) -> None:
    meminfo = tmp_path / "meminfo"
    meminfo.write_text(
        "MemTotal:        3995012 kB\nMemFree:          151234 kB\nMemAvailable:    2048000 kB\n"
    )
    assert available_memory_mb(meminfo) == 2000
    assert available_memory_mb(tmp_path / "missing") is None
