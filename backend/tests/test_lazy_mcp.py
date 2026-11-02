import asyncio
from types import SimpleNamespace

import pytest

from app.ai.prompt_builder import build_prompt
from app.ai.tools import router as router_mod
from app.ai.tools.context import ToolContext
from app.ai.tools.registry import ToolRegistry
from app.services import external_integration_service as eis

REPO = "saiina27/Vibe-Workflow-Intelligence-Platform"


def prompt_for(text=None, turns=None, tracked=None):
    history = turns or [SimpleNamespace(role="user", content=text)]

    return build_prompt(
        memories=[], conversation_summary=None, history=history,
        knowledge_chunks=[], include_memories=False,
        include_knowledge=False, tracked_repos=tracked,
    )


def turn(role, content):
    return SimpleNamespace(role=role, content=content)


@pytest.mark.parametrize(
    "text, github, slack",
    [
        ("hi", False, False),
        ("summarize my uploaded PDF", False, False),
        ("do you remember my name", False, False),
        ("what is the latest Python version", False, False),
        ("explain how JWT works", False, False),
        ("show the latest commits of my repo X", True, False),
        ("show open issues in my repo X", True, False),
        ("5 Oct ko mere repo ke commits kya the", True, False),
        ("search Slack for deployment", False, True),
        ("search Slack channels for dev", False, True),
        ("what did the team say about PR #1 in Slack", True, True),
        ("any update on my vibe project", True, True),
        ("why did we choose Groq as the fallback provider", False, True),
        # "query" is a Slack word; "vibe" alone is not a GitHub signal.
        ("koi query aayi hai kya vibe ke baare mein", False, True),
    ],
)
def test_mcp_needs_follow_the_question(text, github, slack):
    assert ToolRegistry.mcp_needs(prompt_for(text)) == (github, slack)


def test_unsure_cases_connect_everything():
    assert ToolRegistry.mcp_needs(None) == (True, True)
    assert ToolRegistry.mcp_needs("") == (True, True)
    assert ToolRegistry.mcp_needs(prompt_for("यह क्या है")) == (True, True)
    assert ToolRegistry.mcp_needs(
        prompt_for(turns=[turn("assistant", "x")])
    ) == (True, True)


def test_short_followup_keeps_the_previous_question():
    prompt = prompt_for(
        turns=[
            turn("user", "any update on my vibe project"),
            turn("assistant", "Which repository?"),
            turn("user", "vibe"),
        ]
    )

    assert ToolRegistry.mcp_needs(prompt) == (True, True)

    quiet = prompt_for(
        turns=[
            turn("user", "what is the latest Python version"),
            turn("assistant", "3.14"),
            turn("user", "thanks"),
        ]
    )

    assert ToolRegistry.mcp_needs(quiet) == (False, False)


def test_how_does_it_work_needs_github_only_with_a_tracked_repo():
    text = "explain how the provider cooldown works"

    assert ToolRegistry.mcp_needs(prompt_for(text, tracked=[REPO])) == (True, False)
    assert ToolRegistry.mcp_needs(prompt_for(text)) == (False, False)


# ---------------- the router really connects lazily ----------------

class FakeManager:
    def __init__(self):
        self.connected = []

    async def connect_github(self, db, user_id, registry):
        self.connected.append("github")
        return 45

    async def connect_slack(self, db, user_id, registry):
        self.connected.append("slack")
        return 3


class FakePermissions:
    def add_workspace_plugin(self, workspace_id, name):
        pass


@pytest.fixture
def build(monkeypatch):
    manager = FakeManager()

    monkeypatch.setattr(router_mod, "mcp_permission_service", FakePermissions())
    monkeypatch.setattr(eis, "get_user_integration", lambda **kwargs: object())

    router = router_mod.ToolRouter()
    router.mcp_integration_manager = manager

    context = ToolContext(
        db=None, workspace_id=1, user_id=1,
        allowed_tools=frozenset({"github", "slack"}),
    )

    def run(prompt):
        manager.connected.clear()
        asyncio.run(router.build_registry(context, prompt))
        return list(manager.connected)

    return run


def test_greeting_connects_nothing(build):
    assert build(prompt_for("hi")) == []


def test_github_question_connects_only_github(build):
    assert build(prompt_for("show the latest commits of my repo X")) == ["github"]


def test_slack_question_connects_only_slack(build):
    assert build(prompt_for("search Slack for deployment")) == ["slack"]


def test_mixed_question_connects_both(build):
    assert sorted(build(prompt_for("what did the team say about PR #1 in Slack"))) == [
        "github", "slack",
    ]


def test_callers_without_a_prompt_still_connect_both(build):
    assert sorted(build(None)) == ["github", "slack"]
