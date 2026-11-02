from types import SimpleNamespace

import groq
import httpx
import pytest

from app.ai.providers import groq as groq_mod
from app.ai.providers import groq_budget as budget


class Clock:
    def __init__(self, now=1000.0):
        self.now = now

    def __call__(self):
        return self.now


def rate_error(message):
    request = httpx.Request("POST", "https://api.groq.com/x")
    return groq.RateLimitError(
        message, response=httpx.Response(429, request=request), body=None
    )


# ---------------- numbers ----------------

@pytest.mark.parametrize(
    "text, seconds",
    [("2.767s", 2.767), ("1m3.5s", 63.5), ("250ms", 0.25), (None, 0.0), ("", 0.0), ("x", 0.0)],
)
def test_parse_duration(text, seconds):
    assert budget.parse_duration(text) == pytest.approx(seconds)


def test_estimate_refills_linearly_and_unknown_models_are_none():
    clock = Clock(0)
    b = budget.ModelBudget(clock=clock)

    assert b.estimate("m") is None

    b.update("m", 2000, 8000, 30)
    assert b.estimate("m") == pytest.approx(2000)

    clock.now = 15
    assert b.estimate("m") == pytest.approx(5000)

    clock.now = 100
    assert b.estimate("m") == pytest.approx(8000)


# ---------------- ordering ----------------

def test_models_with_enough_room_come_first():
    b = budget.ModelBudget(clock=Clock(0))
    b.update("main", 3000, 8000, 60)
    b.update("big", 7000, 8000, 10)

    assert b.order(["main", "big"], 5000) == ["big", "main"]
    assert b.order(["main", "big"], 2000) == ["main", "big"]


def test_unknown_models_count_as_having_room():
    b = budget.ModelBudget(clock=Clock(0))
    b.update("main", 1000, 8000, 60)

    assert b.order(["main", "big"], 5000) == ["big", "main"]


def test_nothing_has_room_means_the_least_bad_model_first():
    b = budget.ModelBudget(clock=Clock(0))
    b.update("a", 1000, 8000, 60)
    b.update("b", 2500, 8000, 60)

    assert b.order(["a", "b"], 6000) == ["b", "a"]


def test_blocked_models_are_skipped_until_the_block_ends():
    clock = Clock(0)
    b = budget.ModelBudget(clock=clock)

    b.block("main", 3600)
    assert b.order(["main", "big"], 100) == ["big"]

    b.block("big", 3600)
    assert b.order(["main", "big"], 100) == ["main"]

    clock.now = 3601
    assert b.order(["main", "big"], 100) == ["main", "big"]


# ---------------- which models a request may use ----------------

def request(**changes):
    data = dict(
        model="main",
        messages=[{"role": "user", "content": "hello"}],
        max_tokens=2500,
        tools=[{"type": "function"}],
    )
    data.update(changes)
    return data


@pytest.fixture
def fresh(monkeypatch):
    monkeypatch.setattr(budget, "BUDGET", budget.ModelBudget(clock=Clock(0)))
    monkeypatch.delenv("GROQ_MODEL_POOL", raising=False)
    return budget.BUDGET


def test_pool_models_reads_the_env(monkeypatch, fresh):
    assert budget.pool_models() == []

    monkeypatch.setenv("GROQ_MODEL_POOL", "openai/gpt-oss-120b, ,x")
    assert budget.pool_models() == ["openai/gpt-oss-120b", "x"]


def test_without_a_pool_only_the_requested_model_is_used(fresh):
    assert budget.candidate_models("main", request()) == ["main"]


def test_main_calls_use_the_main_model_first_and_helpers_the_pool_first(monkeypatch, fresh):
    monkeypatch.setenv("GROQ_MODEL_POOL", "big")

    assert budget.candidate_models("main", request()) == ["main", "big"]

    helper = request(tools=None, max_tokens=300)
    assert budget.candidate_models("main", helper) == ["big", "main"]


def test_a_nearly_empty_main_bucket_sends_the_call_to_the_pool(monkeypatch, fresh):
    monkeypatch.setenv("GROQ_MODEL_POOL", "big")
    fresh.update("main", 600, 8000, 60)

    big_request = request(messages=[{"role": "user", "content": "x" * 20000}])

    assert budget.candidate_models("main", big_request)[0] == "big"


def test_need_grows_with_the_request():
    small = budget.estimate_need(request())
    big = budget.estimate_need(request(messages=[{"content": "x" * 8000}]))

    assert big > small + 1500


# ---------------- the provider call ----------------

def make_provider(behaviour):
    provider = groq_mod.GroqProvider.__new__(groq_mod.GroqProvider)
    provider.calls = []

    def inner(**kwargs):
        provider.calls.append(kwargs["model"])
        return behaviour(kwargs["model"])

    provider._create_with_rate_limit_retry_inner = inner
    return provider


def test_a_daily_limit_moves_to_the_next_model_and_is_remembered(monkeypatch, fresh):
    monkeypatch.setenv("GROQ_MODEL_POOL", "big")

    def behaviour(model):
        if model == "main":
            raise rate_error("Rate limit reached ... tokens per day (TPD) ...")
        return "ok"

    provider = make_provider(behaviour)

    assert provider._create_with_rate_limit_retry(**request()) == "ok"
    assert provider.calls == ["main", "big"]
    assert fresh.is_blocked("main")

    provider.calls.clear()
    assert provider._create_with_rate_limit_retry(**request()) == "ok"
    assert provider.calls == ["big"]


def test_a_per_minute_limit_also_falls_back_but_does_not_block(monkeypatch, fresh):
    monkeypatch.setenv("GROQ_MODEL_POOL", "big")

    def behaviour(model):
        if model == "main":
            raise rate_error("Rate limit reached ... tokens per minute (TPM) ...")
        return "ok"

    provider = make_provider(behaviour)

    assert provider._create_with_rate_limit_retry(**request()) == "ok"
    assert not fresh.is_blocked("main")


def test_the_error_is_raised_when_no_model_is_left(monkeypatch, fresh):
    def behaviour(model):
        raise rate_error("Rate limit reached ... tokens per day (TPD) ...")

    provider = make_provider(behaviour)

    with pytest.raises(groq.RateLimitError):
        provider._create_with_rate_limit_retry(**request())

    # The first half blocked "main" for an hour (a daily limit). Start the
    # second half with a clean budget.
    monkeypatch.setattr(budget, "BUDGET", budget.ModelBudget(clock=Clock(0)))

    monkeypatch.setenv("GROQ_MODEL_POOL", "big")
    provider = make_provider(behaviour)

    with pytest.raises(groq.RateLimitError):
        provider._create_with_rate_limit_retry(**request())

    assert provider.calls == ["main", "big"]


def test_calls_without_a_model_are_passed_through(fresh):
    provider = groq_mod.GroqProvider.__new__(groq_mod.GroqProvider)
    seen = {}

    provider._create_with_rate_limit_retry_inner = lambda **kw: seen.update(kw) or "ok"

    assert provider._create_with_rate_limit_retry(messages=[]) == "ok"
    assert "model" not in seen


def test_response_headers_update_the_budget_of_the_current_model(fresh):
    budget.CURRENT.model = "main"

    groq_mod._log_http_response(
        SimpleNamespace(
            status_code=200,
            headers={
                "x-ratelimit-remaining-tokens": "3000",
                "x-ratelimit-limit-tokens": "8000",
                "x-ratelimit-reset-tokens": "30s",
            },
        )
    )

    assert 2900 <= fresh.estimate("main") <= 3200

    budget.CURRENT.model = None
