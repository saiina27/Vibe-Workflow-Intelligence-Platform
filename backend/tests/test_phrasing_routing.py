from types import SimpleNamespace

import pytest

from app.ai.prompt_builder import build_prompt
from app.ai.tools.registry import ToolRegistry

TRACKED = ["saiina27/Vibe-Workflow-Intelligence-Platform"]
WRITE = {
    "create_pull_request", "push_files", "create_or_update_file",
    "delete_file", "merge_pull_request",
}
GITHUB = [
    "get_me", "get_file_contents", "search_code", "search_repositories",
    "list_commits", "get_commit", "list_branches", "list_pull_requests",
    "pull_request_read", "list_issues", "issue_read", "search_issues",
    "list_releases", "get_latest_release",
] + sorted(WRITE)
SLACK = ["slack_search_public", "slack_search_public_and_private", "slack_search_channels"]
NATIVE = [
    "search_memory", "search_knowledge", "search_web", "search_chats",
    "search_history", "find_in_code",
]


class FakeTool:
    def __init__(self, name, plugin=None):
        self.name = name
        self.description = f"{name} tool"
        self.parameters = {"type": "object", "properties": {}}
        self.plugin_name = plugin


def judge(text):
    registry = ToolRegistry()

    for name in GITHUB:
        registry.register(FakeTool(name, "github"))

    for name in SLACK:
        registry.register(FakeTool(name, "slack"))

    for name in NATIVE:
        registry.register(FakeTool(name))

    prompt = build_prompt(
        memories=[], conversation_summary=None,
        history=[SimpleNamespace(role="user", content=text)],
        knowledge_chunks=[], include_memories=False, include_knowledge=False,
        tracked_repos=TRACKED,
    )
    github, slack = ToolRegistry.mcp_needs(prompt)
    names = {d.name for d in registry.definitions_for_prompt(prompt)}

    return prompt, github, slack, names


# (text, needs GitHub, needs Slack, tools that must all be there, tools of which one must be there)
CASES = [
    ("show the latest commits of my project", True, False, {"list_commits"}, set()),
    ("last 5 commits dikhao", True, False, {"list_commits"}, set()),
    ("latest commits?", True, False, {"list_commits"}, set()),
    ("whats been pushed recently", True, False, set(), {"list_commits", "search_history"}),
    ("recent commit history of vibe", True, False, set(), {"list_commits", "search_history"}),
    ("kya kya push hua hai latest", True, False, set(), {"list_commits", "search_history"}),
    ("what happened on 6 Oct", False, False, {"search_history"}, set()),
    ("6 oct ko kya hua tha", False, False, {"search_history"}, set()),
    ("what did we do last week", False, False, {"search_history"}, set()),
    ("pichle hafte kya kya kiya", False, False, {"search_history"}, set()),
    ("anything change on october 10th?", False, False, {"search_history"}, set()),
    ("work done yesterday", False, False, {"search_history"}, set()),
    ("what did the team say about deployment on Slack", False, True, {"slack_search_public"}, set()),
    ("slack pe deployment ke baare mein kya baat hui", False, True, {"slack_search_public"}, set()),
    ("any discussion about deploy in slack?", False, True, {"slack_search_public"}, set()),
    ("check the dev-updates channel", False, True, {"slack_search_public"}, set()),
    ("team ne deployment pe kya bola", False, True, {"slack_search_public"}, set()),
    ("did anyone mention the render failure", False, True, {"slack_search_public"}, set()),
    ("explain how the provider cooldown works", True, False, {"find_in_code"}, set()),
    ("cooldown kaise kaam karta hai", True, False, {"find_in_code"}, set()),
    ("how does the router pick a provider", True, False, {"find_in_code"}, set()),
    ("walk me through the rate limiter", True, False, {"find_in_code"}, set()),
    ("what does _in_cooldown do", True, False, {"find_in_code"}, set()),
    ("provider cooldown samjhao", True, False, {"find_in_code"}, set()),
    ("how can I improve the provider cooldown code", True, False, {"find_in_code"}, set()),
    ("is code mein kya better ho sakta hai", True, False, {"find_in_code"}, set()),
    ("refactor ideas for router.py", True, False, {"find_in_code"}, set()),
    ("any problems in my cooldown logic?", True, False, {"find_in_code"}, set()),
    ("code review of the rate limiter", True, False, {"find_in_code"}, set()),
    ("show files changed in PR #1 of my repo Vibe-Workflow-Intelligence-Platform", True, False, {"pull_request_read"}, set()),
    ("pr 1 me kaun si files badli", True, False, {"pull_request_read"}, set()),
    ("what did PR #1 touch", True, False, {"pull_request_read"}, set()),
    ("list changed files pull request 1", True, False, {"pull_request_read"}, set()),
    ("show all open issues in my project", True, False, {"list_issues"}, set()),
    ("koi issue open hai kya", True, False, {"list_issues"}, set()),
    ("any bugs reported?", True, False, {"list_issues"}, set()),
    ("hi", False, False, set(), set()),
    ("thanks", False, False, set(), set()),
    ("ok", False, False, set(), set()),
    ("hii vibe", False, False, set(), set()),
    ("good morning", False, False, set(), set()),
]


@pytest.mark.parametrize("text,github,slack,need_all,need_any", CASES)
def test_each_phrasing_gets_the_right_servers_and_tools(text, github, slack, need_all, need_any):
    _prompt, got_github, got_slack, names = judge(text)

    assert got_github is github, f"github={got_github}"
    assert got_slack is slack, f"slack={got_slack}"
    assert need_all <= names, f"missing {need_all - names}"

    if need_any:
        assert names & need_any, f"none of {need_any} in {names}"

    assert not (names & WRITE)


@pytest.mark.parametrize("text", [
    "create a pull request for my project",
    "push this change to main",
    "PR bana do",
    "delete the old branch",
])
def test_write_requests_never_get_write_tools_and_hear_that_vibe_is_read_only(text):
    prompt, _github, _slack, names = judge(text)

    assert not (names & WRITE)
    assert "read-only" in prompt.lower()


@pytest.mark.parametrize("text", [
    "hi", "what is the capital of France", "work done yesterday",
    "summarize my uploaded PDF",
])
def test_ordinary_questions_do_not_open_the_code_tools(text):
    _prompt, github, _slack, names = judge(text)

    assert github is False
    assert "find_in_code" not in names
