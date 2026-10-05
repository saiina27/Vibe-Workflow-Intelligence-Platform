import pytest

from app.ai.gateway import AIGateway
from app.ai.tools.registry import ToolRegistry
from app.schemas.ai import AIStreamEvent

GITHUB_READ = [
    "get_me", "get_commit", "get_file_contents", "list_branches",
    "list_commits", "list_pull_requests", "list_issues", "issue_read",
    "search_issues", "search_repositories", "search_code",
    "list_releases", "get_latest_release", "list_tags",
    "get_release_by_tag", "pull_request_read",
]

GITHUB_WRITE = [
    "add_comment_to_pending_review", "add_issue_comment",
    "add_reply_to_pull_request_comment", "create_branch",
    "create_or_update_file", "create_pull_request", "create_repository",
    "delete_file", "fork_repository", "issue_write", "merge_pull_request",
    "pull_request_review_write", "push_files", "request_copilot_review",
    "run_secret_scanning", "sub_issue_write", "update_issue_comment",
    "update_pull_request", "update_pull_request_branch",
]

CORE = ["search_web", "search_knowledge", "search_memory"]


class FakeTool:
    def __init__(self, name, plugin_name=None):
        self.name = name
        self.description = f"{name} tool"
        self.parameters = {"type": "object", "properties": {}}
        self.plugin_name = plugin_name


@pytest.fixture
def registry():
    reg = ToolRegistry()
    for name in GITHUB_READ + GITHUB_WRITE:
        reg.register(FakeTool(name, plugin_name="github"))
    for name in CORE:
        reg.register(FakeTool(name))
    return reg


def exposed(registry, prompt):
    return {d.name for d in registry.definitions_for_prompt(prompt)}


REPO = "Vibe-Workflow-Intelligence-Platform"


@pytest.mark.parametrize(
    "prompt, must_have",
    [
        (f"show details of my latest commit in repo {REPO}",
         {"get_me", "list_commits", "get_commit"}),
        (f"list the branches of my repo {REPO}", {"list_branches"}),
        (f"show the README of my repo {REPO}", {"get_file_contents"}),
        (f"show the pull requests of my repo {REPO}",
         {"list_pull_requests"}),
        (f"show open issues in my repo {REPO}",
         {"list_issues", "issue_read"}),
        ('search my github repos for "vibe"',
         {"search_repositories", "search_code"}),
        (f"show releases of my repo {REPO}",
         {"list_releases", "get_latest_release", "list_tags"}),
        (f"show files changed in PR #3 of my repo {REPO}",
         {"pull_request_read"}),
    ],
)
def test_prompt_gets_right_github_tools(registry, prompt, must_have):
    names = exposed(registry, prompt)
    assert must_have <= names
    assert set(CORE) <= names


@pytest.mark.parametrize(
    "prompt",
    [
        f"show details of my latest commit in repo {REPO}",
        f"show open issues in my repo {REPO}",
        'search my github repos for "vibe"',
        f"show releases of my repo {REPO}",
        f"show files changed in PR #3 of my repo {REPO}",
        "only use github: delete the repo and push files",
        "merge the pull request in my repo",
    ],
)
def test_write_tools_never_exposed(registry, prompt):
    assert not (exposed(registry, prompt) & set(GITHUB_WRITE))


def test_github_groups_stay_small(registry):
    for prompt in (
        f"show open issues in my repo {REPO}",
        'search my github repos for "vibe"',
        f"show releases of my repo {REPO}",
        f"show files changed in PR #3 of my repo {REPO}",
    ):
        assert len(exposed(registry, prompt)) <= 9


def test_guard_converts_unexposed_tool_error():
    def boom():
        yield AIStreamEvent(
            type="content", text="hi", model="t", provider="t"
        )
        raise RuntimeError(
            "Tool call validation failed: attempted to call tool "
            "'search_issues' which was not in request.tools"
        )

    events = list(AIGateway._guard_unexposed_tool_errors(boom()))

    assert events[0].text == "hi"
    assert events[-1].type == "content"
    assert "isn't available" in events[-1].text


def test_guard_reraises_other_errors():
    def boom():
        raise RuntimeError("something else")
        yield

    with pytest.raises(RuntimeError):
        list(AIGateway._guard_unexposed_tool_errors(boom()))


# ---- Regression: selection must use only the latest user message ----
from types import SimpleNamespace

from app.ai.prompt_builder import build_prompt


def full_prompt(user_text, earlier=None):
    history = []
    for text in earlier or []:
        history.append(SimpleNamespace(role="user", content=text))
        history.append(SimpleNamespace(role="assistant", content="ok"))
    history.append(SimpleNamespace(role="user", content=user_text))

    return build_prompt(
        memories=[],
        conversation_summary=None,
        history=history,
        knowledge_chunks=[],
        include_memories=False,
        include_knowledge=False,
    )


@pytest.mark.parametrize(
    "user_text, earlier, must_have, must_not",
    [
        ('search my github repos for "vibe"', None,
         {"search_repositories", "search_code"}, {"list_issues"}),
        (f"show the latest release and tags of my repo {REPO}", None,
         {"list_releases", "list_tags"}, {"list_issues"}),
        (f"show open issues in my repo {REPO}", None,
         {"list_issues", "issue_read"}, {"list_releases"}),
        (f"show the latest release and tags of my repo {REPO}",
         [f"show open issues in my repo {REPO}"],
         {"list_releases", "list_tags"}, {"list_issues"}),
        (f"show the README of my repo {REPO}", None,
         {"get_file_contents"}, {"list_issues", "list_releases"}),
    ],
)
def test_full_prompt_uses_latest_message_only(
    registry, user_text, earlier, must_have, must_not
):
    names = exposed(registry, full_prompt(user_text, earlier))
    assert must_have <= names
    assert not (must_not & names)
    assert not (names & set(GITHUB_WRITE))


def test_prompt_keeps_only_recent_history_and_latest_message():
    earlier = [f"old question number {i}" for i in range(20)]
    prompt = full_prompt("show the branches of my repo X", earlier)

    assert "old question number 0" not in prompt
    assert "show the branches of my repo X" in prompt
    assert "RESPONSE FORMAT RULES" in prompt
