from types import SimpleNamespace

import pytest

from app.ai.prompt_builder import build_prompt
from app.ai.tools.registry import MAX_EXPOSED_TOOLS, ToolRegistry

REPO = "saiina27/Vibe-Workflow-Intelligence-Platform"
WRITE = {"create_pull_request", "push_files", "create_or_update_file"}

GITHUB = [
    "get_me", "get_file_contents", "search_code", "search_repositories",
    "list_commits", "create_pull_request", "push_files", "create_or_update_file",
]
NATIVE = ["search_web", "search_knowledge", "search_memory", "find_in_code"]


class FakeTool:
    def __init__(self, name, plugin=None):
        self.name = name
        self.description = f"{name} tool"
        self.parameters = {"type": "object", "properties": {}}
        self.plugin_name = plugin


def prompt_for(text, tracked=None):
    return build_prompt(
        memories=[], conversation_summary=None,
        history=[SimpleNamespace(role="user", content=text)],
        knowledge_chunks=[], include_memories=False,
        include_knowledge=False, tracked_repos=tracked,
    )


def exposed(text, tracked=None):
    registry = ToolRegistry()

    for name in GITHUB:
        registry.register(FakeTool(name, "github"))

    for name in NATIVE:
        registry.register(FakeTool(name))

    return {d.name for d in registry.definitions_for_prompt(prompt_for(text, tracked))}


@pytest.mark.parametrize(
    "text",
    [
        "how can I improve the provider cooldown code",
        "refactor the router module",
        "what could be optimized in my code",
        "review the code of backend/app/ai/router.py",
    ],
)
def test_improvement_questions_get_the_rule_and_the_code_tools(text):
    prompt = prompt_for(text, [REPO])
    names = exposed(text, [REPO])

    assert "CODE IMPROVEMENT" in prompt
    assert "Suggested change (not applied)" in prompt
    assert {"find_in_code", "get_file_contents"} <= names
    assert not (names & WRITE)
    assert len(names) <= MAX_EXPOSED_TOOLS
    assert ToolRegistry.mcp_needs(prompt) == (True, False)


def test_without_a_tracked_repo_improvement_words_open_no_github_tools():
    names = exposed("how can I improve my essay")

    assert "get_file_contents" not in names and "search_code" not in names


def test_ordinary_questions_do_not_get_the_improvement_rule():
    for text in ("hi", "show the latest commits of my repo X", "summarize my uploaded PDF"):
        assert "CODE IMPROVEMENT" not in prompt_for(text, [REPO])


def test_the_rule_says_suggest_only():
    prompt = prompt_for("how can I improve the router", [REPO])

    assert "Vibe cannot\n  change code" in prompt
    assert "at most 4 suggestions" in prompt
