import inspect
from types import SimpleNamespace

import pytest

from app.ai.chat_title_generator import ChatTitleGenerator
from app.ai.providers import groq as groq_mod
from app.ai.tools.context import ToolContext
from app.ai.tools.executor import ToolExecutor
from app.ai.tools.registry import ToolRegistry
from app.ai.tools.result_compactor import compact_tool_result
from app.ai.topic_detector import TopicDetector
from app.models.enums import TaskComplexity, TaskType
from app.services import conversation_service as cs


class FakeGateway:
    def __init__(self, text):
        self.text = text
        self.request = None

    def generate(self, request):
        self.request = request
        return SimpleNamespace(content=self.text)


def test_title_runs_on_groq_with_room_for_reasoning():
    generator = ChatTitleGenerator.__new__(ChatTitleGenerator)
    generator.gateway = FakeGateway('"Latest GitHub commits"')

    assert generator.generate("User: show commits") == "Latest GitHub commits"

    request = generator.gateway.request
    assert request.task_type == TaskType.CODE
    assert request.complexity == TaskComplexity.SIMPLE
    assert request.max_tokens >= 200


def test_topic_runs_on_groq_with_room_for_reasoning():
    detector = TopicDetector.__new__(TopicDetector)
    detector.gateway = FakeGateway("Backend Development")

    assert detector.detect("fix my FastAPI route") == "Backend Development"

    request = detector.gateway.request
    assert request.task_type == TaskType.CODE
    assert request.max_tokens >= 200


def test_unknown_topic_falls_back_to_general():
    detector = TopicDetector.__new__(TopicDetector)
    detector.gateway = FakeGateway("Cooking")

    assert detector.detect("hello") == "General"


# ---------------- reasoning effort switch ----------------

def set_model(monkeypatch, model):
    monkeypatch.setattr("app.core.config.settings.groq_model", model, raising=False)


def test_reasoning_effort_is_off_by_default(monkeypatch):
    monkeypatch.delenv("GROQ_REASONING_EFFORT", raising=False)
    set_model(monkeypatch, "openai/gpt-oss-20b")

    assert groq_mod._effort_kwargs() == {}


def test_reasoning_effort_applies_to_gpt_oss_only(monkeypatch):
    monkeypatch.setenv("GROQ_REASONING_EFFORT", "LOW")

    set_model(monkeypatch, "openai/gpt-oss-20b")
    assert groq_mod._effort_kwargs() == {"extra_body": {"reasoning_effort": "low"}}

    set_model(monkeypatch, "llama-3.3-70b-versatile")
    assert groq_mod._effort_kwargs() == {}


def test_invalid_reasoning_effort_is_ignored(monkeypatch):
    monkeypatch.setenv("GROQ_REASONING_EFFORT", "turbo")
    set_model(monkeypatch, "openai/gpt-oss-20b")

    assert groq_mod._effort_kwargs() == {}


def test_every_groq_request_call_carries_the_switch():
    source = inspect.getsource(groq_mod)

    assert source.count("**_effort_kwargs()") == 6
    assert "Groq {kind} in" in source


# ---------------- tool timing ----------------

class EchoTool:
    name = "echo"
    description = "echo"
    parameters = {"type": "object", "properties": {}}
    plugin_name = None

    def execute(self, **kwargs):
        return {"echo": kwargs}


def test_tool_runs_are_timed_and_results_are_unchanged(capsys):
    registry = ToolRegistry()
    registry.register(EchoTool())

    executor = ToolExecutor(
        registry, ToolContext(db=None, workspace_id=1, user_id=1)
    )

    assert executor.execute("echo", {"a": 1}) == {"echo": {"a": 1}}
    assert "⏱️ tool echo ran in" in capsys.readouterr().out


# ---------------- compaction note and quiet timeouts ----------------

def test_partial_list_note_says_it_is_not_the_total():
    import json

    class Block:
        def __init__(self, text):
            self.text = text
            self.type = "text"

    payload = [{"sha": f"{i:040x}", "message": "x" * 80} for i in range(100)]
    result = {"success": True, "data": {"content": [{"type": "text", "text": json.dumps(payload)}]}}

    out = compact_tool_result(result, 3000)

    assert "of 100 items" in out["_note"]
    assert "not the total" in out["_note"]


def test_timeouts_print_one_line_instead_of_a_traceback():
    source = inspect.getsource(cs.stream_ai_response)

    assert "except TimeoutError:" in source
    assert "title timed out" in source and "topic timed out" in source
