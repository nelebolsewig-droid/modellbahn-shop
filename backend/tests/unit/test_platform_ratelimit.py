"""The sliding-window limiter behind the 429 answers of the login routes."""

import pytest

from modellbahn.platform.ratelimit import RateLimiter


class ManualClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def clock() -> ManualClock:
    return ManualClock()


def limiter(clock: ManualClock, *, limit: int = 3, window: float = 60.0) -> RateLimiter:
    return RateLimiter(limit=limit, window_seconds=window, clock=clock)


def test_requests_up_to_the_limit_pass(clock: ManualClock) -> None:
    subject = limiter(clock)

    assert [subject.hit("10.0.0.1") for _ in range(3)] == [None, None, None]


def test_the_next_request_learns_how_long_to_wait(clock: ManualClock) -> None:
    subject = limiter(clock)
    subject.hit("10.0.0.1")
    clock.now += 20
    subject.hit("10.0.0.1")
    subject.hit("10.0.0.1")

    # The oldest request leaves the window 60 s after it came, 40 s from now.
    assert subject.hit("10.0.0.1") == pytest.approx(40.0)


def test_the_window_slides_instead_of_resetting(clock: ManualClock) -> None:
    subject = limiter(clock)
    subject.hit("10.0.0.1")
    clock.now += 30
    subject.hit("10.0.0.1")
    subject.hit("10.0.0.1")

    clock.now += 30
    assert subject.hit("10.0.0.1") is None  # the first request has left the window
    assert subject.hit("10.0.0.1") is not None  # the other two have not


def test_a_rejected_request_does_not_extend_the_wait(clock: ManualClock) -> None:
    subject = limiter(clock, limit=1)
    subject.hit("10.0.0.1")
    for _ in range(10):
        clock.now += 5
        assert subject.hit("10.0.0.1") is not None

    clock.now += 10
    assert subject.hit("10.0.0.1") is None


def test_clients_are_counted_separately(clock: ManualClock) -> None:
    subject = limiter(clock, limit=1)
    subject.hit("10.0.0.1")

    assert subject.hit("10.0.0.1") is not None
    assert subject.hit("10.0.0.2") is None


def test_a_limit_of_zero_switches_the_limiter_off(clock: ManualClock) -> None:
    subject = limiter(clock, limit=0)

    assert not subject.enabled
    assert all(subject.hit("10.0.0.1") is None for _ in range(100))


def test_clients_that_went_quiet_are_forgotten(clock: ManualClock) -> None:
    subject = limiter(clock, limit=5)
    for client in range(1000):
        subject.hit(f"10.0.{client // 256}.{client % 256}")
    clock.now += 61

    for _ in range(24):  # the 1024th call sweeps
        subject.hit("10.9.9.9")

    assert list(subject._hits) == ["10.9.9.9"]
