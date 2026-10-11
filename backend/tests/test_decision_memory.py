from types import SimpleNamespace

import pytest

from app.ai import memory_extractor
from app.ai.memory_retriever import MemoryRetriever
from app.ai.prompt_builder import build_prompt
from app.ai.tools.context import ToolContext
from app.ai.tools.memory_tool import MemoryTool
from app.ai.tools.registry import MAX_EXPOSED_TOOLS, ToolRegistry


def mem(i, kind):
    return SimpleNamespace(
        id=i,
        memory_type=SimpleNamespace(value=kind),
        title=f"t{i}",
        content=f"c{i}",
        importance=5,
        confidence=1.0,
    )


# ---------------- retriever ----------------

def make_retriever(rows):
    seen = {}

    class FakeRepo:
        def similarity_search(self, **kwargs):
            seen.update(kwargs)
            return rows

    r = MemoryRetriever.__new__(MemoryRetriever)
    r.embedding_service = SimpleNamespace(generate_embedding=lambda q: [0.0])
    r.embedding_repository = FakeRepo()
    return r, seen


def test_retriever_without_filter_is_unchanged():
    rows = [mem(1, "fact"), mem(2, "decision")]
    r, seen = make_retriever(rows)

    assert r.retrieve(db=None, workspace_id=1, query="q", limit=5) == rows
    assert seen["limit"] == 5


def test_retriever_filters_by_type_and_fetches_more():
    rows = [mem(1, "fact"), mem(2, "decision"), mem(3, "decision"), mem(4, "preference")]
    r, seen = make_retriever(rows)

    out = r.retrieve(db=None, workspace_id=1, query="q", limit=5, memory_type="decision")

    assert [m.id for m in out] == [2, 3]
    assert seen["limit"] == 20


# ---------------- tool ----------------

def make_tool(rows):
    calls = {}

    class FakeRetriever:
        def retrieve(self, **kwargs):
            calls.update(kwargs)
            return rows

    tool = MemoryTool.__new__(MemoryTool)
    tool.context = ToolContext(db=None, workspace_id=1, user_id=1)
    tool.retriever = FakeRetriever()
    return tool, calls


def test_memory_type_is_passed_and_normalized():
    tool, calls = make_tool([mem(1, "decision")])
    out = tool.execute(query="fallback", memory_type=" Decision ")

    assert calls["memory_type"] == "decision"
    assert out["count"] == 1


def test_unknown_or_null_memory_type_means_no_filter():
    tool, calls = make_tool([])

    tool.execute(query="x", memory_type="banana")
    assert calls["memory_type"] is None

    tool.execute(query="x", memory_type=None)
    assert calls["memory_type"] is None


def test_schema_has_nullable_memory_type_and_query_still_required():
    tool, _ = make_tool([])
    params = tool.parameters

    assert "null" in params["properties"]["memory_type"]["type"]
    assert params["required"] == ["query"]
    assert "decision" in tool.description


# ---------------- extractor prompts ----------------

class FakeGateway:
    last_prompt = None

    def generate(self, request):
        FakeGateway.last_prompt = request.prompt
        return SimpleNamespace(content='{"memories": []}')


def test_auto_extraction_prompt_has_decision_format(monkeypatch):
    monkeypatch.setattr(memory_extractor, "AIGateway", FakeGateway)
    memory_extractor.extract_memories("we decided to use Groq")

    prompt = FakeGateway.last_prompt
    assert "Decision: <what was decided>" in prompt
    assert "Never invent a reason" in prompt


def test_explicit_extraction_prompt_has_decision_rule(monkeypatch):
    monkeypatch.setattr(memory_extractor, "AIGateway", FakeGateway)
    memory_extractor.extract_memory("remember we chose Groq as fallback")

    assert "Never invent a reason" in FakeGateway.last_prompt


# ---------------- prompt and registry ----------------

def full_prompt(text):
    return build_prompt(
        memories=[], conversation_summary=None,
        history=[SimpleNamespace(role="user", content=text)],
        knowledge_chunks=[], include_memories=False,
        include_knowledge=False,
    )


def test_prompt_has_decision_and_explain_rules():
    prompt = full_prompt("hi")

    assert "DECISION QUESTIONS AND EXPLAIN MODE" in prompt
    assert 'memory_type\n  "decision"' in prompt
    assert "reason was not recorded" in prompt
    assert "What it is, Why it is this way, How it works" in prompt
    assert "General alternatives" in prompt


class FakeTool:
    def __init__(self, name, plugin=None):
        self.name = name
        self.description = f"{name} tool"
        self.parameters = {"type": "object", "properties": {}}
        self.plugin_name = plugin


def exposed(text):
    reg = ToolRegistry()
    for n in ("get_me", "list_commits", "list_pull_requests",
              "search_repositories", "create_pull_request"):
        reg.register(FakeTool(n, "github"))
    for n in ("slack_search_public", "slack_search_channels"):
        reg.register(FakeTool(n, "slack"))
    for n in ("search_web", "search_knowledge", "search_memory",
              "search_chats", "search_history"):
        reg.register(FakeTool(n))
    return {d.name for d in reg.definitions_for_prompt(full_prompt(text))}


def test_decision_question_gets_memory_slack_history_and_chats():
    names = exposed("why did we make this decision about the fallback provider")

    assert {"search_memory", "slack_search_public",
            "search_history", "search_chats"} <= names
    assert "create_pull_request" not in names
    assert len(names) <= MAX_EXPOSED_TOOLS
