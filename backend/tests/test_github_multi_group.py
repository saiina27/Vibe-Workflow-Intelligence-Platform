import pytest

from app.ai.tools.registry import MAX_EXPOSED_TOOLS, ToolRegistry

READ = [
    "get_me", "get_commit", "get_file_contents", "list_branches",
    "list_commits", "list_pull_requests", "list_issues", "issue_read",
    "search_issues", "search_repositories", "search_code",
    "list_releases", "get_latest_release", "list_tags",
    "get_release_by_tag", "pull_request_read",
]
WRITE = [
    "create_pull_request", "delete_file", "merge_pull_request",
    "push_files", "issue_write", "create_branch",
]
CORE = ["search_web", "search_knowledge", "search_memory"]


class FakeTool:
    def __init__(self, name):
        self.name = name
        self.description = f"{name} tool"
        self.parameters = {"type": "object", "properties": {}}
        self.plugin_name = "github"


@pytest.fixture
def registry():
    reg = ToolRegistry()
    for name in READ + WRITE + CORE:
        reg.register(FakeTool(name))
    return reg


def exposed(registry, prompt):
    return {d.name for d in registry.definitions_for_prompt(prompt)}


REPO = "my repo Vibe-Workflow-Intelligence-Platform"


def test_issues_and_releases_together(registry):
    names = exposed(registry, f"show open issues and releases of {REPO}")
    assert {"list_issues", "issue_read"} <= names
    assert {"list_releases", "list_tags"} <= names


def test_single_topic_still_single_group(registry):
    names = exposed(registry, f"show open issues in {REPO}")
    assert "list_issues" in names
    assert "list_releases" not in names


def test_budget_never_exceeded(registry):
    names = exposed(
        registry,
        f"show issues, releases, files changed in PR #2 and search code in {REPO}",
    )
    assert len(names) <= MAX_EXPOSED_TOOLS
    assert set(CORE) <= names


@pytest.mark.parametrize(
    "prompt",
    [
        f"show open issues and releases of {REPO}",
        f"issues, releases, PR #1 files changed and search code in {REPO}",
        f"create a pull request in {REPO}",
    ],
)
def test_multi_group_never_exposes_write_tools(registry, prompt):
    assert not (exposed(registry, prompt) & set(WRITE))
