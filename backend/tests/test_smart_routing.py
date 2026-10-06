import time
from types import SimpleNamespace

import pytest

from app.ai.prompt_builder import build_prompt
from app.ai.router import ProviderRouter
from app.ai.tools.registry import MAX_EXPOSED_TOOLS, ToolRegistry
from app.core.config import settings
from app.schemas.ai import AIRequest

GITHUB = [
    "get_me", "get_commit", "get_file_contents", "list_branches",
    "list_commits", "list_pull_requests", "list_issues", "issue_read",
    "search_issues", "search_repositories", "pull_request_read",
    "create_pull_request", "merge_pull_request",
]
SLACK = ["slack_search_public", "slack_search_channels"]
CORE = ["search_web", "search_knowledge", "search_memory"]


class FakeTool:
    def __init__(self, name, plugin=None):
        self.name = name
        self.description = f"{name} tool"
        self.parameters = {"type": "object", "properties": {}}
        self.plugin_name = plugin


def registry():
    reg = ToolRegistry()
    for n in GITHUB:
        reg.register(FakeTool(n, "github"))
    for n in SLACK:
        reg.register(FakeTool(n, "slack"))
    for n in CORE:
        reg.register(FakeTool(n))
    return reg


def exposed(text):
    prompt = build_prompt(
        memories=[],
        conversation_summary=None,
        history=[SimpleNamespace(role="user", content=text)],
        knowledge_chunks=[],
        include_memories=False,
        include_knowledge=False,
    )
    return {d.name for d in registry().definitions_for_prompt(prompt)}


def test_project_update_gets_github_slack_and_memory():
    names = exposed("any update on my vibe project")
    assert {"list_commits", "slack_search_public", "search_memory"} <= names
    assert len(names) <= MAX_EXPOSED_TOOLS
    assert not (names & {"create_pull_request", "merge_pull_request"})


def test_commit_and_pr_question_gets_github_and_memory():
    names = exposed("is there any new commit or pull request on my project")
    assert {"list_commits", "list_pull_requests", "search_memory"} <= names


def test_query_about_vibe_gets_slack_and_memory_without_github():
    names = exposed("any query about vibe from the team")
    assert {"slack_search_public", "search_memory"} <= names
    assert "list_commits" not in names


def test_slack_named_gets_slack():
    assert "slack_search_public" in exposed("what did we decide in Slack")


def test_generic_question_has_no_github_tools():
    names = exposed("what is the latest Python version")
    assert "list_commits" not in names
    assert "search_web" in names


def test_prompt_has_tool_choice_rules():
    prompt = build_prompt(
        memories=[],
        conversation_summary=None,
        history=[SimpleNamespace(role="user", content="hi")],
        knowledge_chunks=[],
        include_memories=False,
        include_knowledge=False,
    )
    assert "TOOL CHOICE RULES" in prompt
    assert "slack_search_public" in prompt


@pytest.fixture
def router(monkeypatch):
    monkeypatch.setattr(settings, "fallback_provider", "groq", raising=False)
    monkeypatch.setattr(settings, "gemini_model", "g-model", raising=False)
    monkeypatch.setattr(settings, "groq_model", "q-model", raising=False)
    r = ProviderRouter.__new__(ProviderRouter)
    r._cooldowns = {}
    r.registry = SimpleNamespace(providers={"gemini": "G", "groq": "Q"})
    r.primary = "G"
    r.fallback = "Q"
    return r


def test_quota_error_starts_cooldown(router):
    req = SimpleNamespace(model="g-model")
    router._record_failure(req, RuntimeError("429 RESOURCE_EXHAUSTED quota"))
    assert router._in_cooldown("gemini")


def test_overload_error_starts_short_cooldown(router):
    req = SimpleNamespace(model="g-model")
    router._record_failure(req, RuntimeError("503 UNAVAILABLE"))
    assert router._in_cooldown("gemini")


def test_other_errors_and_fallback_provider_do_not_start_cooldown(router):
    router._record_failure(SimpleNamespace(model="g-model"), RuntimeError("bad json"))
    router._record_failure(SimpleNamespace(model="q-model"), RuntimeError("429 quota"))
    assert not router._in_cooldown("gemini")
    assert not router._in_cooldown("groq")


def test_cooldown_expires(router):
    router._cooldowns["gemini"] = time.monotonic() - 1
    assert not router._in_cooldown("gemini")


def test_select_provider_uses_fallback_during_cooldown(router):
    router._get_model_for_provider = lambda n: f"{n}-model"
    router._cooldowns["gemini"] = time.monotonic() + 100
    req = AIRequest(prompt="hi")
    assert router._select_provider(req) == "Q"
    assert req.model == "groq-model"
