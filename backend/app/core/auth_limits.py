import math
import os
import threading
import time
from collections import deque


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name)

    if raw is None or raw.strip() == "":
        return default

    try:
        value = int(raw.strip())
    except ValueError:
        return default

    return value if value >= 0 else default


class SlidingWindow:
    """Counts events per key inside a time window. limit 0 means off."""

    def __init__(self, limit: int, window_seconds: int, clock=time.time):
        self.limit = limit
        self.window = window_seconds
        self._clock = clock
        self._lock = threading.Lock()
        self._events: dict[str, deque] = {}

    def _trim(self, key: str, now: float):
        events = self._events.get(key)

        if events is None:
            return None

        while events and now - events[0] >= self.window:
            events.popleft()

        if not events:
            del self._events[key]
            return None

        return events

    def wait_seconds(self, key: str) -> int:
        """Seconds until the key may try again; 0 when it is allowed now."""

        if not self.limit:
            return 0

        now = self._clock()

        with self._lock:
            events = self._trim(key, now)

            if events is None or len(events) < self.limit:
                return 0

            return max(1, int(math.ceil(self.window - (now - events[0]))))

    def hit(self, key: str) -> None:
        if not self.limit:
            return

        now = self._clock()

        with self._lock:
            events = self._trim(key, now)

            if events is None:
                events = self._events.setdefault(key, deque())

            events.append(now)

            if len(self._events) > 5000:
                for other in list(self._events):
                    self._trim(other, now)

            if len(self._events) > 20000:
                self._events.clear()


def wait_text(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds} second" + ("" if seconds == 1 else "s")

    minutes = int(math.ceil(seconds / 60))

    return f"{minutes} minute" + ("" if minutes == 1 else "s")


def client_ip(request) -> str:
    client = getattr(request, "client", None)

    return getattr(client, "host", None) or "unknown"


login_failures = SlidingWindow(_int_env("LOGIN_FAILURES_PER_10MIN", 10), 600)
signup_per_ip = SlidingWindow(_int_env("SIGNUPS_PER_IP_PER_HOUR", 5), 3600)
signup_global = SlidingWindow(_int_env("SIGNUPS_PER_DAY", 30), 86400)
