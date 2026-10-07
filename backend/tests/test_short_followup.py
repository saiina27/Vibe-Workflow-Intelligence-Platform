from types import SimpleNamespace

from app.ai.prompt_builder import build_prompt
from app.ai.tools.registry import ToolRegistry

GITHUB = ["get_me", "list_commits", "list_pull_requests",
          "search_repositories", "create_pull_request"]
CORE = ["search_web", "search_knowledge", "search_memory"]


class FakeTool:
    def __init__(self, name, plugin=None):
        self.name = name
        self.description = f"{name} tool"
        self.parameters = {"type": "object", "properties": {}}
        self.plugin_name = plugin


def exposed(turns):
    history = [SimpleNamespace(role=r, content=c) for r, c in turns]
    prompt = build_prompt(
        memories=[], conversation_summary=None, history=history,
        knowledge_chunks=[], include_memories=False,
        include_knowledge=False,
    )
    reg = ToolRegistry()
    for n in GITHUB:
        reg.register(FakeTool(n, "github"))
    for n in CORE:
        reg.register(FakeTool(n))
    return {d.name for d in reg.definitions_for_prompt(prompt)}


def test_short_followup_keeps_github_tools():
    names = exposed([
        ("user", "is there any new commit or pull request on my project"),
        ("assistant", "Which repository do you mean?"),
        ("user", "vibe"),
    ])
    assert {"get_me", "list_commits", "search_repositories"} <= names
    assert "create_pull_request" not in names


def test_short_followup_after_non_github_stays_non_github():
    names = exposed([
        ("user", "what is the latest Python version"),
        ("assistant", "3.14"),
        ("user", "thanks"),
    ])
    assert "list_commits" not in names
    assert "search_web" in names


def test_long_latest_message_ignores_history():
    names = exposed([
        ("user", "show the branches of my repo X"),
        ("assistant", "ok"),
        ("user", "what is the latest Python version"),
    ])
    assert "list_commits" not in names
