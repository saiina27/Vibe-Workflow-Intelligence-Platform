import math
import os
import threading
import time
from collections import deque
from dataclasses import dataclass

IST_OFFSET_SECONDS = 19800
DAY_SECONDS = 86400


@dataclass(frozen=True)
class RateDecision:
    allowed: bool
    reason: str | None = None
    message: str = ""
    retry_after: int = 0


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name)

    if raw is None or raw.strip() == "":
        return default

    try:
        value = int(raw.strip())
    except ValueError:
        return default

    return value if value >= 0 else default


def _ids_env(name: str) -> set[int]:
    ids: set[int] = set()

    for part in (os.getenv(name) or "").split(","):
        part = part.strip()

        if part.isdigit():
            ids.add(int(part))

    return ids


class AIRateLimiter:
    """
    Protects the free AI quota: per user per minute, per user per day
    and for everyone per day (the day follows IST). A limit of 0 means
    "off". Counters live in memory, so they reset when the server
    restarts and are not shared between server instances.
    """

    def __init__(
        self,
        per_minute: int = 4,
        per_day: int = 15,
        global_per_day: int = 40,
        exempt_user_ids: set[int] | None = None,
        clock=time.time,
    ):
        self.per_minute = per_minute
        self.per_day = per_day
        self.global_per_day = global_per_day
        self.exempt = set(exempt_user_ids or ())
        self._clock = clock

        self._lock = threading.Lock()
        self._recent: dict[int, deque] = {}
        self._user_day: dict[int, int] = {}
        self._global_day = 0
        self._day = ""

    @classmethod
    def from_env(cls) -> "AIRateLimiter":
        return cls(
            per_minute=_int_env("RATE_LIMIT_PER_MINUTE", 4),
            per_day=_int_env("RATE_LIMIT_PER_DAY", 15),
            global_per_day=_int_env("RATE_LIMIT_GLOBAL_PER_DAY", 40),
            exempt_user_ids=_ids_env("RATE_LIMIT_EXEMPT_USER_IDS"),
        )

    @staticmethod
    def _day_key(now: float) -> str:
        return time.strftime("%Y-%m-%d", time.gmtime(now + IST_OFFSET_SECONDS))

    @staticmethod
    def _seconds_to_midnight(now: float) -> int:
        return DAY_SECONDS - int((now + IST_OFFSET_SECONDS) % DAY_SECONDS)

    def check(self, user_id: int) -> RateDecision:
        """Return the decision and count the request only when it is allowed."""

        if user_id in self.exempt:
            return RateDecision(True)

        now = self._clock()

        with self._lock:
            day = self._day_key(now)

            if day != self._day:
                self._day = day
                self._user_day = {}
                self._global_day = 0

            window = self._recent.setdefault(user_id, deque())

            while window and now - window[0] >= 60:
                window.popleft()

            if self.per_minute and len(window) >= self.per_minute:
                wait = max(1, int(math.ceil(60 - (now - window[0]))))

                return RateDecision(
                    False,
                    "per_minute",
                    f"You are sending questions too quickly. Please wait {wait} seconds.",
                    wait,
                )

            used = self._user_day.get(user_id, 0)

            if self.per_day and used >= self.per_day:
                return RateDecision(
                    False,
                    "per_day",
                    f"You have reached today's limit of {self.per_day} questions. "
                    "It resets at midnight IST.",
                    self._seconds_to_midnight(now),
                )

            if self.global_per_day and self._global_day >= self.global_per_day:
                return RateDecision(
                    False,
                    "global",
                    "Vibe's free AI quota for today is used up. Please try again tomorrow.",
                    self._seconds_to_midnight(now),
                )

            window.append(now)
            self._user_day[user_id] = used + 1
            self._global_day += 1

            return RateDecision(True)


ai_rate_limiter = AIRateLimiter.from_env()
