import pytest

from app.ai.tools.registry import MAX_EXPOSED_TOOLS, ToolRegistry

GITHUB = [
    "get_me", "get_commit", "get_file_contents", "list_branches",
    "list_commits", "list_pull_requests", "list_issues", "issue_read",
    "search_issues", "search_repositories", "search_code",
    "list_releases", "get_latest_release", "list_tags",
    "get_release_by_tag", "pull_request_read",
    "create_pull_request", "merge_pull_request",
]
SLACK = [
    "slack_search_public",
    "slack_search_public_and_private",
    "slack_search_channels",
]
CORE = ["search_web", "search_knowledge", "search_memory"]


class FakeTool:
    def __init__(self, name, plugin=None):
        self.name = name
        self.description = f"{name} tool"
        self.parameters = {"type": "object", "properties": {}}
        self.plugin_name = plugin


@pytest.fixture
def registry():
    reg = ToolRegistry()
    for n in GITHUB:
        reg.register(FakeTool(n, "github"))
    for n in SLACK:
        reg.register(FakeTool(n, "slack"))
    for n in CORE:
        reg.register(FakeTool(n))
    return reg


def exposed(registry, prompt):
    return {d.name for d in registry.definitions_for_prompt(prompt)}


def test_github_and_slack_question_gets_both(registry):
    names = exposed(registry, "what did the team say about the PR in Slack for my repo X")
    assert "list_pull_requests" in names
    assert "slack_search_public" in names
    assert len(names) <= MAX_EXPOSED_TOOLS


def test_github_only_question_has_no_slack_tools(registry):
    names = exposed(registry, "show the branches of my repo X")
    assert not (names & set(SLACK))


def test_budget_respected_with_slack(registry):
    names = exposed(registry, "show open issues and releases of my repo X from Slack")
    assert len(names) <= MAX_EXPOSED_TOOLS


def test_slack_mix_never_exposes_github_write(registry):
    names = exposed(registry, "create a pull request and tell Slack about my repo X")
    assert not (names & {"create_pull_request", "merge_pull_request"})
