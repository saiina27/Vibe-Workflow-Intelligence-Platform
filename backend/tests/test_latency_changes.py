import asyncio
import time
from types import SimpleNamespace

import pytest

from app.ai.memory_filter import worth_extracting
from app.ai.tools.registry import ToolRegistry
from app.mcp import tool_discovery as td
from app.services import conversation_service as cs


# ---------------- extraction filter ----------------

@pytest.mark.parametrize(
    "text",
    [
        "I decided to use Groq as the fallback provider",
        "We decided to use Groq because Gemini has a small quota",
        "humne Groq ko fallback rakha kyunki Gemini ka quota kam hai",
        "my project is called Vibe",
        "I'm building a FastAPI app",
        "remember that tabs are fine",
        "mujhe Python pasand hai",
        "यह मेरा project है",
    ],
)
def test_messages_that_state_something_are_extracted(text):
    assert worth_extracting(text)


@pytest.mark.parametrize(
    "text",
    [
        "hi", "thanks!", "ok", "", "   ",
        "what can you do?",
        "explain how JWT works",
        "show the latest commits of the repo",
        "summarize the uploaded PDF",
        "search Slack for deployment",
        "show the latest commits of my project",
        "what is my name?",
        "Do you remember my name",
        "why did we choose Groq as the fallback provider",
        "kya mera project deploy ho gaya?",
    ],
)
def test_generic_messages_skip_the_extraction_call(text):
    assert not worth_extracting(text)


# ---------------- the streaming flow ----------------

class FakeDb:
    def commit(self):
        pass

    def refresh(self, obj):
        pass

    def rollback(self):
        pass


@pytest.fixture
def flow(monkeypatch):
    order = []
    messages = []
    chat = SimpleNamespace(id=1, title="New Chat", topic=None, workspace_id=5)

    def forbidden(*args, **kwargs):
        raise AssertionError("retrieval must not run: its result is never used")

    def fake_stream(prompt, context):
        yield SimpleNamespace(type="content", text="Hello ")
        yield SimpleNamespace(type="content", text="world")

    def fake_title(conversation):
        order.append("title")
        return "A title"

    def fake_topic(message):
        order.append("topic")
        return "general"

    def fake_extract(text):
        order.append("extract")
        return [{"memory_type": "decision"}]

    monkeypatch.setattr(cs, "_get_authorized_chat", lambda db, chat_id, user_id: chat)
    monkeypatch.setattr(cs.memory_cleanup_service, "expire_memories", lambda db: None)
    monkeypatch.setattr(
        cs, "create_message",
        lambda db, chat_id, role, content: messages.append((role, content)),
    )
    monkeypatch.setattr(
        cs, "get_messages_for_ai",
        lambda db, chat_id: [SimpleNamespace(role="user", content="x")],
    )
    monkeypatch.setattr(cs.summary_service, "get_summary", lambda db, chat_id: None)
    monkeypatch.setattr(
        cs.summary_service, "should_generate_summary",
        lambda message_count, last_summary_count: False,
    )
    monkeypatch.setattr(cs, "tracked_repo_names", lambda db, workspace_id: [])
    monkeypatch.setattr(cs.memory_retriever, "retrieve", forbidden)
    monkeypatch.setattr(cs.knowledge_retriever, "retrieve", forbidden)
    monkeypatch.setattr(cs, "generate_ai_response_stream_with_tools", fake_stream)
    monkeypatch.setattr(cs.chat_title_generator, "generate", fake_title)
    monkeypatch.setattr(cs.topic_detector, "detect", fake_topic)
    monkeypatch.setattr(cs, "extract_memories", fake_extract)
    monkeypatch.setattr(
        cs.chat_repository, "update_title",
        lambda db, chat, title: order.append("title_saved"),
    )
    monkeypatch.setattr(
        cs.memory_decision_service, "process_memories",
        lambda db, workspace_id, memories: order.append("memories_saved"),
    )

    def run(content):
        for _ in cs.stream_ai_response(
            db=FakeDb(), chat_id=1, content=content, user_id=1, with_tools=True,
        ):
            order.append("yield")

    return SimpleNamespace(run=run, order=order, messages=messages, chat=chat)


def test_title_topic_and_extraction_run_with_the_answer_and_finish_before_done(flow):
    flow.run("we decided to use Groq as the fallback provider")

    last_yield = max(i for i, e in enumerate(flow.order) if e == "yield")

    assert {"title", "topic", "extract"} <= set(flow.order)
    assert flow.order.index("title_saved") > last_yield
    assert flow.order.index("memories_saved") > last_yield
    assert flow.chat.topic == "general"


def test_both_messages_are_saved(flow):
    flow.run("we decided to use Groq")

    assert flow.messages == [
        ("user", "we decided to use Groq"),
        ("assistant", "Hello world"),
    ]


def test_generic_message_skips_extraction_but_still_titles_the_chat(flow):
    flow.run("hi")

    assert "extract" not in flow.order
    assert "title" in flow.order and "topic" in flow.order


def test_existing_title_and_topic_are_not_generated_again(flow):
    flow.chat.title = "Existing chat"
    flow.chat.topic = "python"

    flow.run("we decided to use Groq")

    assert "title" not in flow.order and "topic" not in flow.order
    assert "extract" in flow.order


def test_a_failing_post_task_does_not_break_the_others(flow, monkeypatch):
    def broken(conversation):
        raise RuntimeError("title model down")

    monkeypatch.setattr(cs.chat_title_generator, "generate", broken)

    flow.run("we decided to use Groq")

    assert "topic" in flow.order and "memories_saved" in flow.order
    assert flow.messages[-1] == ("assistant", "Hello world")


# ---------------- MCP tool list cache ----------------

class FakeClient:
    def __init__(self):
        self.calls = 0

    def list_tools(self):
        self.calls += 1
        return [SimpleNamespace(name="get_me"), SimpleNamespace(name="search_commits")]


class FakeAdapter:
    def __init__(self, client, tool, plugin_name):
        self.name = tool.name
        self.description = "d"
        self.parameters = {"type": "object", "properties": {}}
        self.plugin_name = plugin_name

    def execute(self, **kwargs):
        return None


def discover(client):
    registry = ToolRegistry()
    count = asyncio.run(td.MCPToolDiscovery(client, "github").discover(registry))
    return count, registry


def test_tool_list_is_fetched_once_per_client(monkeypatch):
    monkeypatch.setattr(td, "MCPToolAdapter", FakeAdapter)
    client = FakeClient()

    first, _ = discover(client)
    second, registry = discover(client)

    assert client.calls == 1
    assert first == second == 1  # search_commits is still excluded
    assert registry.get("get_me").plugin_name == "github"


def test_a_new_client_or_an_expired_cache_fetches_again(monkeypatch):
    monkeypatch.setattr(td, "MCPToolAdapter", FakeAdapter)

    discover(FakeClient())
    other = FakeClient()
    discover(other)
    assert other.calls == 1

    client = FakeClient()
    discover(client)

    real = time.monotonic()
    monkeypatch.setattr(td.time, "monotonic", lambda: real + 700)
    discover(client)

    assert client.calls == 2


def test_explicit_save_requests_are_extracted_even_in_question_form():
    assert worth_extracting("Can you remember that I prefer tabs")
    assert worth_extracting("save this: we use Postgres")
    assert not worth_extracting("Can you remember that I prefer tabs?")


def test_post_tasks_have_timeouts():
    import inspect

    source = inspect.getsource(cs.stream_ai_response)

    assert "title_future.result(timeout=6)" in source
    assert "topic_future.result(timeout=6)" in source
    assert "memory_future.result(timeout=20)" in source
