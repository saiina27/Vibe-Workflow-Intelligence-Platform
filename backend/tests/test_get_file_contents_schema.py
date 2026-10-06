from app.ai.gateway import (
    INVALID_TOOL_ARGS_MESSAGE,
    UNEXPOSED_TOOL_MESSAGE,
    AIGateway,
)
from app.ai.tools.registry import ToolRegistry
from app.schemas.ai import AIStreamEvent


class FakeTool:
    def __init__(self, name, parameters=None):
        self.name = name
        self.description = f"{name} tool"
        self.parameters = parameters or {
            "type": "object",
            "properties": {"owner": {"type": "string"}},
        }
        self.plugin_name = "github"


def make_registry():
    reg = ToolRegistry()
    reg.register(
        FakeTool(
            "get_file_contents",
            {
                "type": "object",
                "properties": {
                    "owner": {"type": "string"},
                    "path": {"type": "string"},
                    "fields": {"type": "array"},
                },
                "required": ["owner", "fields"],
            },
        )
    )
    reg.register(
        FakeTool(
            "list_commits",
            {
                "type": "object",
                "properties": {"fields": {"type": "array"}},
            },
        )
    )
    for n in ("search_web", "search_knowledge", "search_memory"):
        reg.register(FakeTool(n))
    return reg


def defs_by_name(prompt):
    return {
        d.name: d
        for d in make_registry().definitions_for_prompt(prompt)
    }


def test_fields_hidden_for_get_file_contents_only():
    defs = defs_by_name("show the README of my repo X")

    file_params = defs["get_file_contents"].parameters
    assert "fields" not in file_params["properties"]
    assert "fields" not in file_params["required"]
    assert "owner" in file_params["properties"]

    assert "fields" in defs["list_commits"].parameters["properties"]


def test_original_tool_schema_not_modified():
    reg = make_registry()
    reg.definitions_for_prompt("show the README of my repo X")

    original = reg.get("get_file_contents").parameters
    assert "fields" in original["properties"]


def run_guard(message):
    def boom():
        raise RuntimeError(message)
        yield

    events = list(AIGateway._guard_unexposed_tool_errors(boom()))
    assert isinstance(events[-1], AIStreamEvent)
    return events[-1].text


def test_schema_mismatch_gets_invalid_args_message():
    text = run_guard(
        "Tool call validation failed: parameters for tool "
        "get_file_contents did not match schema"
    )
    assert text == INVALID_TOOL_ARGS_MESSAGE


def test_unexposed_tool_keeps_unexposed_message():
    text = run_guard(
        "Tool call validation failed: attempted to call tool "
        "'x' which was not in request.tools"
    )
    assert text == UNEXPOSED_TOOL_MESSAGE
