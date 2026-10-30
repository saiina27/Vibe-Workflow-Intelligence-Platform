from types import SimpleNamespace

import pytest

from app.ai.prompt_builder import build_prompt
from app.ai.tools.registry import MAX_EXPOSED_TOOLS, ToolRegistry

REPO = "saiina27/Vibe-Workflow-Intelligence-Platform"

GITHUB_READ = [
    "get_me", "get_commit", "get_file_contents", "list_branches",
    "list_commits", "list_pull_requests", "list_issues", "issue_read",
    "search_issues", "search_repositories", "search_code",
    "list_releases", "get_latest_release", "list_tags",
    "get_release_by_tag", "pull_request_read",
]
GITHUB_WRITE = [
    "create_pull_request", "create_branch", "create_or_update_file",
    "delete_file", "merge_pull_request", "push_files", "issue_write",
    "add_issue_comment", "update_pull_request", "fork_repository",
]
SLACK = [
    "slack_search_public", "slack_search_public_and_private",
    "slack_search_channels",
]
NATIVE = [
    "search_web", "search_knowledge", "search_memory",
    "search_chats", "search_history", "find_in_code",
]

TABLE = "### What I Can Help With"
TOOL_CHOICE = "TOOL CHOICE RULES"
DECISION = "DECISION QUESTIONS AND EXPLAIN MODE"
TRACKED = "TRACKED REPOSITORIES:"

# Questions whose behaviour was checked on the live app. If routing
# changes, this list shows what moved.
CASES = [
    dict(id="latest-commits", prompt="show the latest commits of my repo X",
         has={"list_commits"}, lacks={"search_history"},
         sections_in=[TOOL_CHOICE], sections_out=[TABLE]),
    dict(id="open-issues", prompt="show open issues in my repo X",
         has={"list_issues", "issue_read"}, lacks={"list_releases"}),
    dict(id="releases-and-tags", prompt="show the latest release and tags of my repo X",
         has={"list_releases", "list_tags"}, lacks={"list_issues"}),
    dict(id="pr-files-changed", prompt="show files changed in PR #3 of my repo X",
         has={"pull_request_read"}),
    dict(id="repo-search", prompt='search my github repos for "vibe"',
         has={"search_repositories", "search_code"}),
    dict(id="date-question", prompt="5 Oct ko humne kya changes kiye the",
         has={"search_history"}, lacks={"list_commits", "get_me"},
         sections_in=[TOOL_CHOICE], sections_out=[TABLE]),
    dict(id="pdf", prompt="summarize my uploaded PDF",
         has={"search_knowledge"}, lacks={"list_commits"},
         sections_out=[TOOL_CHOICE, TABLE]),
    dict(id="memory", prompt="do you remember my name",
         has={"search_memory"}, lacks={"list_commits"},
         sections_out=[TOOL_CHOICE]),
    dict(id="web", prompt="what is the latest Python version",
         has={"search_web"}, lacks={"list_commits"},
         sections_out=[TOOL_CHOICE]),
    dict(id="github-plus-slack", prompt="what did the team say about PR #1 in Slack",
         has={"slack_search_public", "pull_request_read"}),
    dict(id="write-request", prompt="create a pull request for my project",
         lacks={"create_pull_request", "push_files", "merge_pull_request"}),
    dict(id="explain-own-code", prompt="explain how the provider cooldown works",
         tracked=True, has={"find_in_code", "get_file_contents"},
         lacks={"list_commits"}, sections_in=[TRACKED, DECISION],
         sections_out=[TABLE]),
    dict(id="explain-general-concept", prompt="explain how JWT works",
         lacks={"search_code", "get_file_contents", "list_commits"},
         sections_in=[DECISION], sections_out=[TOOL_CHOICE, TRACKED]),
    dict(id="decision-why", prompt="why did we choose Groq as the fallback provider",
         has={"search_memory"}, sections_in=[DECISION]),
    dict(id="capability", prompt="what can you do?",
         lacks={"list_commits"}, sections_in=[TABLE]),
    dict(id="project-update", prompt="any update on my vibe project",
         has={"list_commits", "slack_search_public", "search_memory"}),
    dict(id="earlier-chat",
         prompt="pichhli chat mein rate limiting ke baare mein humne kya discuss kiya tha",
         has={"search_chats"}, lacks={"list_commits"}),
    dict(id="existence-question", prompt="rate limiting ke baare mein koi commit hua tha kya",
         has={"search_history"}, lacks={"list_commits"}),
]


class FakeTool:
    def __init__(self, name, plugin=None):
        self.name = name
        self.description = f"{name} tool"
        self.parameters = {"type": "object", "properties": {}}
        self.plugin_name = plugin


def registry():
    reg = ToolRegistry()

    for name in GITHUB_READ + GITHUB_WRITE:
        reg.register(FakeTool(name, "github"))

    for name in SLACK:
        reg.register(FakeTool(name, "slack"))

    for name in NATIVE:
        reg.register(FakeTool(name))

    return reg


def prompt_for(text, tracked):
    return build_prompt(
        memories=[], conversation_summary=None,
        history=[SimpleNamespace(role="user", content=text)],
        knowledge_chunks=[], include_memories=False,
        include_knowledge=False,
        tracked_repos=[REPO] if tracked else None,
    )


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_golden_routing(case):
    prompt = prompt_for(case["prompt"], case.get("tracked", False))
    names = {d.name for d in registry().definitions_for_prompt(prompt)}

    assert case.get("has", set()) <= names, f"missing: {case.get('has', set()) - names}"
    assert not (case.get("lacks", set()) & names), f"unexpected: {case.get('lacks', set()) & names}"

    assert not (names & set(GITHUB_WRITE)), "a GitHub write tool was exposed"
    assert len(names) <= MAX_EXPOSED_TOOLS

    for section in case.get("sections_in", []):
        assert section in prompt, f"prompt is missing {section!r}"

    for section in case.get("sections_out", []):
        assert section not in prompt, f"prompt should not have {section!r}"


def test_golden_set_is_big_enough():
    assert len(CASES) >= 15
    assert len({c["id"] for c in CASES}) == len(CASES)
