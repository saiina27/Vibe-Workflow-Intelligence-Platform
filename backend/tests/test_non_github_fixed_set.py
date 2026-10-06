from types import SimpleNamespace

import pytest

from app.ai.prompt_builder import build_prompt
from app.ai.tools.registry import ToolRegistry

CORE = ["search_web", "search_knowledge", "search_memory"]
GITHUB = ["get_me", "list_commits", "list_issues", "create_pull_request"]
SLACK = ["slack_search_public"]


class FakeTool:
    def __init__(self, name, plugin=None):
        self.name = name
        self.description = f"{name} tool"
        self.parameters = {"type": "object", "properties": {}}
        self.plugin_name = plugin


def make_registry():
    reg = ToolRegistry()
    for n in CORE:
        reg.register(FakeTool(n))
    for n in GITHUB:
        reg.register(FakeTool(n, "github"))
    for n in SLACK:
        reg.register(FakeTool(n, "slack"))
    return reg


def full_prompt(text):
    return build_prompt(
        memories=[],
        conversation_summary=None,
        history=[SimpleNamespace(role="user", content=text)],
        knowledge_chunks=[],
        include_memories=False,
        include_knowledge=False,
    )


@pytest.mark.parametrize(
    "text",
    [
        "summarize my uploaded PDF",
        "do you remember my name",
        "what is the latest Python version",
        "hello",
    ],
)
def test_non_github_gets_core_and_slack_only(text):
    names = {
        d.name for d in make_registry().definitions_for_prompt(full_prompt(text))
    }
    assert names == set(CORE) | set(SLACK)


def test_github_prompt_still_gets_github_tools_not_write():
    names = {
        d.name
        for d in make_registry().definitions_for_prompt(
            full_prompt("show open issues in my repo X")
        )
    }
    assert "list_issues" in names
    assert "create_pull_request" not in names
    assert set(CORE) <= names
