import json
import os
import re
import threading
import time

DEFAULT_LIMIT = 8000
DAILY_BLOCK_SECONDS = 3600
HELPER_MAX_TOKENS = 400

# The model used by the Groq call running in this thread (set before a
# call, read by the HTTP response hook that records the rate-limit headers).
CURRENT = threading.local()

_DURATION = re.compile(r"(?:(\d+)m)?([\d.]+)(ms|s)")


def parse_duration(text) -> float:
    """Groq's "1m3.5s" / "2.767s" / "250ms" as seconds (0 when unknown)."""

    if not text:
        return 0.0

    match = _DURATION.search(str(text))

    if not match:
        return 0.0

    minutes = int(match.group(1) or 0)
    value = float(match.group(2))
    seconds = value / 1000 if match.group(3) == "ms" else value

    return minutes * 60 + seconds


class ModelBudget:
    """
    Remembers how many tokens each Groq model has left this minute, from
    the rate-limit headers of its last response, and which models hit
    their daily limit. Everything is in memory and per process.
    """

    def __init__(self, clock=time.monotonic):
        self._clock = clock
        self._lock = threading.Lock()
        self._state = {}
        self._blocked = {}

    def update(self, model, remaining, limit, reset_seconds) -> None:
        with self._lock:
            self._state[model] = (
                float(remaining),
                float(limit or DEFAULT_LIMIT),
                float(reset_seconds or 0),
                self._clock(),
            )

    def estimate(self, model):
        """Tokens probably available now; None when nothing is known."""

        with self._lock:
            state = self._state.get(model)

        if state is None:
            return None

        remaining, limit, reset, at = state

        if reset <= 0:
            return limit

        elapsed = self._clock() - at

        return remaining + (limit - remaining) * min(1.0, elapsed / reset)

    def has_room(self, model, need) -> bool:
        """True when the model is not blocked and probably has `need` tokens."""

        if self.is_blocked(model):
            return False

        estimate = self.estimate(model)

        return estimate is None or estimate >= need

    def block(self, model, seconds=DAILY_BLOCK_SECONDS) -> None:
        with self._lock:
            self._blocked[model] = self._clock() + seconds

    def is_blocked(self, model) -> bool:
        with self._lock:
            until = self._blocked.get(model)

        return until is not None and self._clock() < until

    def order(self, preferred, need):
        """Models to try, best first: enough room, then most room."""

        usable = [m for m in preferred if not self.is_blocked(m)]

        if not usable:
            return list(preferred[:1])

        estimates = {m: self.estimate(m) for m in usable}

        enough = [
            m for m in usable
            if estimates[m] is None or estimates[m] >= need
        ]

        rest = sorted(
            (m for m in usable if m not in enough),
            key=lambda m: -(estimates[m] or 0),
        )

        return enough + rest


BUDGET = ModelBudget()


def pool_models() -> list:
    """Extra models from GROQ_MODEL_POOL (comma separated). Empty = off."""

    raw = os.getenv("GROQ_MODEL_POOL") or ""

    return [part.strip() for part in raw.split(",") if part.strip()]


def estimate_need(kwargs) -> int:
    """Rough input tokens of a request (about 0.9 of chars/4, plus a margin)."""

    try:
        chars = len(json.dumps(kwargs.get("messages") or [], default=str))
        chars += len(json.dumps(kwargs.get("tools") or [], default=str))
    except Exception:
        chars = 0

    return int(chars / 4 * 0.9) + 150


def is_helper(kwargs) -> bool:
    """Small calls without tools (title, topic): they should not use the main bucket."""

    max_tokens = kwargs.get("max_tokens") or 10**9

    return not kwargs.get("tools") and max_tokens <= HELPER_MAX_TOKENS


def candidate_models(main, kwargs) -> list:
    pool = [m for m in pool_models() if m != main]

    if not main or not pool:
        return [main]

    preferred = (pool + [main]) if is_helper(kwargs) else ([main] + pool)

    return BUDGET.order(preferred, estimate_need(kwargs))
