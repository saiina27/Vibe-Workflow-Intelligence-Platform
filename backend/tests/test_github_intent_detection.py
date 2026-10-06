from types import SimpleNamespace

import pytest

from app.ai.prompt_builder import build_prompt
from app.ai.tools.registry import ToolRegistry

WRITE = ["create_pull_request", "delete_file", "merge_pull_request", "push_files"]
READ = [
    "get_me", "get_commit", "get_file_contents", "list_branches",
    "list_commits", "list_pull_requests", "list_issues", "issue_read",
    "search_issues", "search_repositories",
]
CORE = ["search_web", "search_knowledge", "search_memory"]


class FakeTool:
    def __init__(self, name):
        self.name = name
        self.description = f"{name} tool"
        self.parameters = {"type": "object", "properties": {}}
        self.plugin_name = "github"


def full_prompt(user_text):
    history = [SimpleNamespace(role="user", content=user_text)]
    return build_prompt(
        memories=[],
        conversation_summary=None,
        history=history,
        knowledge_chunks=[],
        include_memories=False,
        include_knowledge=False,
    )


@pytest.mark.parametrize(
    "text",
    [
        "show my project issues",
        "list my open bugs",
        "show my latest release",
        "create a pull request for my project",
        "show PR 2 changes",
        "what changed in my pull request",
        "show the README of my project",
    ],
)
def test_github_intent_detected(text):
    assert ToolRegistry._is_github_intent(full_prompt(text))


@pytest.mark.parametrize(
    "text",
    [
        "what is the latest Python version",
        "release notes of React 19",
        "what is a git tag",
        "summarize my uploaded pdf",
        "hello",
        "write a report on sales",
    ],
)
def test_non_github_not_detected_even_with_system_prompt(text):
    assert not ToolRegistry._is_github_intent(full_prompt(text))


def test_project_issues_prompt_gets_issue_tools_and_no_write_tools():
    reg = ToolRegistry()
    for name in WRITE + READ + CORE:
        reg.register(FakeTool(name))

    names = {
        d.name
        for d in reg.definitions_for_prompt(full_prompt("show my project issues"))
    }

    assert {"list_issues", "issue_read"} <= names
    assert not (names & set(WRITE))
