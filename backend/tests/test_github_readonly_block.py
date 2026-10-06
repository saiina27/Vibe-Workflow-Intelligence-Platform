from types import SimpleNamespace

import pytest

from app.ai.tool_calling import _guard_read_only
from app.ai.tools.registry import ToolRegistry, is_blocked_write_tool

WRITE = [
    "add_comment_to_pending_review", "add_issue_comment",
    "add_reply_to_pull_request_comment", "create_branch",
    "create_or_update_file", "create_pull_request", "create_repository",
    "delete_file", "fork_repository", "issue_write", "merge_pull_request",
    "pull_request_review_write", "push_files", "request_copilot_review",
    "run_secret_scanning", "sub_issue_write", "update_issue_comment",
    "update_pull_request", "update_pull_request_branch",
]

READ = [
    "get_me", "get_commit", "get_file_contents", "list_branches",
    "list_commits", "list_pull_requests", "list_issues", "issue_read",
    "search_issues", "search_repositories", "search_code",
    "list_releases", "get_latest_release", "list_tags",
    "get_release_by_tag", "pull_request_read", "get_tag",
    "search_web", "search_knowledge", "search_memory",
]


class FakeTool:
    def __init__(self, name):
        self.name = name
        self.description = f"{name} tool"
        self.parameters = {"type": "object", "properties": {}}
        self.plugin_name = "github"


@pytest.mark.parametrize("name", WRITE)
def test_write_tools_are_blocked(name):
    assert is_blocked_write_tool(name)


@pytest.mark.parametrize("name", READ)
def test_read_tools_are_not_blocked(name):
    assert not is_blocked_write_tool(name)


@pytest.mark.parametrize(
    "prompt",
    [
        "create a pull request for my project",
        "delete the branch github-readonly-complete",
        "merge my pull request",
        "push a file test.md to my repo",
        "hello there",
        "only use github: push files",
    ],
)
def test_write_tools_never_exposed_for_any_prompt(prompt):
    reg = ToolRegistry()
    for name in WRITE + READ:
        reg.register(FakeTool(name))

    names = {d.name for d in reg.definitions_for_prompt(prompt)}

    assert not (names & set(WRITE))


def test_executor_guard_blocks_write_and_allows_read():
    calls = []

    def fake_execute(tool_name, arguments=None):
        calls.append(tool_name)
        return "ok"

    executor = SimpleNamespace(execute=fake_execute)
    _guard_read_only(executor)

    with pytest.raises(PermissionError):
        executor.execute(tool_name="push_files", arguments={})

    assert executor.execute(tool_name="list_commits", arguments={}) == "ok"
    assert calls == ["list_commits"]
