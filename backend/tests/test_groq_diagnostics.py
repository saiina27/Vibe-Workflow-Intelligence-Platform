from types import SimpleNamespace

from app.ai.providers import groq as groq_mod


def test_rate_limit_headers_are_logged(capsys):
    response = SimpleNamespace(
        status_code=429,
        headers={
            "retry-after": "12",
            "x-ratelimit-remaining-tokens": "120",
            "x-ratelimit-reset-tokens": "12.3s",
        },
    )

    groq_mod._log_http_response(response)
    out = capsys.readouterr().out

    assert "Groq HTTP 429" in out
    assert "remaining tokens 120" in out
    assert "retry-after 12" in out


def test_logging_never_raises_on_odd_responses():
    groq_mod._log_http_response(None)
    groq_mod._log_http_response(SimpleNamespace())


def test_request_size_and_reasoning_are_logged(capsys):
    provider = groq_mod.GroqProvider.__new__(groq_mod.GroqProvider)
    provider.client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **kw: "ok"))
    )

    result = provider._create_with_rate_limit_retry(
        model="openai/gpt-oss-20b",
        messages=[{"role": "user", "content": "x" * 400}],
        tools=[{"type": "function", "function": {"name": "t"}}],
        extra_body={"reasoning_effort": "low"},
    )

    out = capsys.readouterr().out

    assert result == "ok"
    assert "message tokens" in out and "tool-definition tokens" in out
    assert "reasoning: low" in out


def test_request_without_tools_or_effort_is_logged_too(capsys):
    provider = groq_mod.GroqProvider.__new__(groq_mod.GroqProvider)
    provider.client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **kw: "ok"))
    )

    provider._create_with_rate_limit_retry(model="m", messages=[])

    assert "reasoning: default" in capsys.readouterr().out


def test_client_logs_headers_and_falls_back_to_a_plain_client(monkeypatch):
    seen = []

    class FakeGroq:
        def __init__(self, **kwargs):
            seen.append(kwargs)

    monkeypatch.setattr(groq_mod, "Groq", FakeGroq)

    groq_mod._make_client()
    assert "http_client" in seen[-1]

    import groq

    monkeypatch.delattr(groq, "DefaultHttpxClient", raising=False)

    groq_mod._make_client()
    assert "http_client" not in seen[-1]
