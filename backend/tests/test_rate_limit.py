import threading

import pytest

from app.core.rate_limit import AIRateLimiter


class Clock:
    def __init__(self, now=1000.0):
        self.now = now

    def __call__(self):
        return self.now


def make(clock, **kwargs):
    defaults = dict(per_minute=0, per_day=0, global_per_day=0)
    defaults.update(kwargs)
    return AIRateLimiter(clock=clock, **defaults)


def test_per_minute_blocks_then_allows_after_the_window():
    clock = Clock(1000)
    limiter = make(clock, per_minute=3)

    for _ in range(3):
        assert limiter.check(1).allowed
        clock.now += 1

    blocked = limiter.check(1)
    assert not blocked.allowed and blocked.reason == "per_minute"
    assert 1 <= blocked.retry_after <= 60
    assert str(blocked.retry_after) in blocked.message

    clock.now = 1061
    assert limiter.check(1).allowed


def test_per_minute_is_per_user():
    limiter = make(Clock(), per_minute=1)

    assert limiter.check(1).allowed
    assert not limiter.check(1).allowed
    assert limiter.check(2).allowed


def test_per_day_blocks_and_resets_at_midnight_ist():
    clock = Clock(66500)  # 23:41 IST, 200 seconds before midnight
    limiter = make(clock, per_day=2)

    assert limiter.check(1).allowed
    assert limiter.check(1).allowed

    blocked = limiter.check(1)
    assert blocked.reason == "per_day" and "2 questions" in blocked.message
    assert 0 < blocked.retry_after <= 200

    clock.now += 200
    assert limiter.check(1).allowed


def test_global_cap_counts_only_allowed_requests():
    clock = Clock(66500)
    limiter = make(clock, global_per_day=2)

    assert limiter.check(1).allowed
    assert limiter.check(2).allowed

    blocked = limiter.check(3)
    assert blocked.reason == "global" and "tomorrow" in blocked.message

    clock.now += 200
    assert limiter.check(3).allowed


def test_blocked_requests_do_not_use_up_the_quota():
    limiter = make(Clock(), per_minute=1, global_per_day=2)

    assert limiter.check(1).allowed
    for _ in range(10):
        assert not limiter.check(1).allowed

    assert limiter.check(2).allowed


def test_exempt_users_are_unlimited_and_not_counted():
    limiter = make(Clock(), per_minute=1, global_per_day=1, exempt_user_ids={7})

    for _ in range(5):
        assert limiter.check(7).allowed

    assert limiter.check(8).allowed
    assert not limiter.check(9).allowed


def test_zero_turns_every_limit_off():
    limiter = make(Clock())

    assert all(limiter.check(1).allowed for _ in range(1000))


def test_from_env_reads_values_and_ignores_bad_ones(monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_PER_MINUTE", "7")
    monkeypatch.setenv("RATE_LIMIT_PER_DAY", "abc")
    monkeypatch.setenv("RATE_LIMIT_GLOBAL_PER_DAY", "-3")
    monkeypatch.setenv("RATE_LIMIT_EXEMPT_USER_IDS", "4, 9,x, ")

    limiter = AIRateLimiter.from_env()

    assert limiter.per_minute == 7
    assert limiter.per_day == 15
    assert limiter.global_per_day == 40
    assert limiter.exempt == {4, 9}


def test_defaults_when_nothing_is_set(monkeypatch):
    for name in (
        "RATE_LIMIT_PER_MINUTE", "RATE_LIMIT_PER_DAY",
        "RATE_LIMIT_GLOBAL_PER_DAY", "RATE_LIMIT_EXEMPT_USER_IDS",
    ):
        monkeypatch.delenv(name, raising=False)

    limiter = AIRateLimiter.from_env()

    assert (limiter.per_minute, limiter.per_day, limiter.global_per_day) == (4, 15, 40)
    assert limiter.exempt == set()


def test_parallel_requests_never_exceed_the_limit():
    limiter = AIRateLimiter(per_minute=10, per_day=0, global_per_day=0)
    results = []

    def worker():
        results.append(limiter.check(1).allowed)

    threads = [threading.Thread(target=worker) for _ in range(50)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert results.count(True) == 10
