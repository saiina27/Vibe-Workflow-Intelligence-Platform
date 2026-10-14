from types import SimpleNamespace

from app.ai.prompt_builder import build_prompt
from app.ai.tools.registry import MAX_EXPOSED_TOOLS, ToolRegistry

GITHUB = [
    "get_me", "get_file_contents", "search_code", "search_repositories",
    "list_commits", "list_branches", "list_pull_requests", "get_commit",
    "create_pull_request", "push_files",
]
CORE = ["search_web", "search_knowledge", "search_memory"]


class FakeTool:
    def __init__(self, name, plugin=None):
        self.name = name
        self.description = f"{name} tool"
        self.parameters = {"type": "object", "properties": {}}
        self.plugin_name = plugin


def prompt_for(text):
    return build_prompt(
        memories=[], conversation_summary=None,
        history=[SimpleNamespace(role="user", content=text)],
        knowledge_chunks=[], include_memories=False,
        include_knowledge=False,
    )


def exposed(text):
    reg = ToolRegistry()
    for name in GITHUB:
        reg.register(FakeTool(name, "github"))
    for name in CORE:
        reg.register(FakeTool(name))

    return {d.name for d in reg.definitions_for_prompt(prompt_for(text))}


def test_code_explanation_in_a_repo_exposes_code_reading_tools():
    names = exposed("explain how the provider cooldown works in my repo X")

    assert {"get_me", "search_repositories", "search_code",
            "get_file_contents"} <= names
    assert "list_commits" not in names
    assert not (names & {"create_pull_request", "push_files"})
    assert len(names) <= MAX_EXPOSED_TOOLS


def test_other_wording_also_triggers_it():
    names = exposed("how does the router work in my repo X")
    assert "search_code" in names


def test_commit_and_readme_questions_are_unchanged():
    commits = exposed("show the latest commits of my repo X")
    assert "list_commits" in commits
    assert "search_code" not in commits

    readme = exposed("explain the README of my repo X")
    assert "get_file_contents" in readme
    assert "search_code" not in readme


def test_workflow_in_a_repo_name_is_not_a_trigger():
    names = exposed("show the branches of my repo Vibe-Workflow-Intelligence-Platform")
    assert "list_branches" in names
    assert "search_code" not in names


def test_implementation_rule_is_in_the_explain_prompt_only():
    prompt = prompt_for("explain how the provider cooldown works")

    assert "IMPLEMENTATION QUESTIONS" in prompt
    assert "General idea, not from your code" in prompt
    assert "not how it is\n  implemented" in prompt
    assert "IMPLEMENTATION QUESTIONS" not in prompt_for("hi")
