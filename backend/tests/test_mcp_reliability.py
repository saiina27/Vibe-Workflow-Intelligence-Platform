import asyncio
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.ai.tools import executor as executor_mod
from app.ai.tools.context import ToolContext
from app.ai.tools.executor import ToolExecutor
from app.ai.tools.registry import ToolRegistry
from app.ai.tools.tool_schema import compact_definition, hide_params
from app.api.routes import oauth as oauth_routes
from app.dependencies.auth import get_current_user
from app.dependencies.database import get_db
from app.mcp import prewarm
from app.mcp.tool_adapter import MCPToolAdapter
from app.schemas.ai import ToolDefinition

GENERIC = "Server returned an error response"


# ---------------- hidden `fields` ----------------

def schema_with_fields():
    return {
        "type": "object",
        "properties": {
            "owner": {"type": "string"},
            "fields": {
                "type": "array",
                "items": {"type": "string", "enum": ["sha", "html_url"]},
            },
        },
        "required": ["owner", "fields"],
    }


def test_fields_is_hidden_from_the_model_and_other_params_stay():
    out = hide_params(schema_with_fields())

    assert set(out["properties"]) == {"owner"}
    assert out["required"] == ["owner"]
    assert "fields" in schema_with_fields()["properties"]


def test_schemas_without_fields_are_untouched():
    plain = {"type": "object", "properties": {"owner": {"type": "string"}}}

    assert hide_params(plain) is plain
    assert hide_params("text") == "text"


def test_compact_definition_hides_fields():
    definition = ToolDefinition(
        name="list_commits", description="d", parameters=schema_with_fields()
    )

    assert "fields" not in compact_definition(definition).parameters["properties"]


class FakeTool:
    def __init__(self, name, plugin=None):
        self.name = name
        self.description = "d"
        self.parameters = schema_with_fields()
        self.plugin_name = plugin


def test_only_mcp_tools_lose_fields_in_the_registry():
    from types import SimpleNamespace as NS
    from app.ai.prompt_builder import build_prompt

    registry = ToolRegistry()
    registry.register(FakeTool("list_commits", "github"))
    registry.register(FakeTool("get_me", "github"))
    registry.register(FakeTool("search_memory"))

    prompt = build_prompt(
        [], None, [NS(role="user", content="show the latest commits of my repo X")],
        [], False, False,
    )
    defs = {d.name: d for d in registry.definitions_for_prompt(prompt)}

    assert "fields" not in defs["list_commits"].parameters["properties"]
    assert "fields" in defs["search_memory"].parameters["properties"]


# ---------------- one retry for a transient MCP error ----------------

class FakeClient:
    def __init__(self, failures, message=GENERIC):
        self.failures = failures
        self.message = message
        self.calls = 0

    def call_tool(self, tool_name, arguments):
        self.calls += 1

        if self.calls <= self.failures:
            raise RuntimeError(self.message)

        return {"ok": True}


class AllowAll:
    def is_tool_allowed(self, plugin_name, tool_name, context):
        return True


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr(executor_mod.time, "sleep", lambda seconds: None)


def run(tool_name, client):
    adapter = MCPToolAdapter(
        client=client,
        tool=SimpleNamespace(
            name=tool_name, description="d",
            input_schema={"type": "object", "properties": {}},
        ),
        plugin_name="github",
    )
    registry = ToolRegistry()
    registry.register(adapter)

    executor = ToolExecutor(
        registry,
        ToolContext(db=None, workspace_id=1, user_id=1),
        mcp_permission_service=AllowAll(),
    )

    return executor.execute(tool_name, {})


def test_one_generic_error_is_retried_and_succeeds():
    client = FakeClient(failures=1)

    assert run("pull_request_read", client) == {"ok": True}
    assert client.calls == 2


def test_two_generic_errors_end_in_an_error_after_two_tries():
    client = FakeClient(failures=5)

    with pytest.raises(RuntimeError, match="execution failed"):
        run("pull_request_read", client)

    assert client.calls == 2


def test_other_errors_are_not_retried():
    client = FakeClient(failures=5, message="Not Found")

    with pytest.raises(RuntimeError):
        run("pull_request_read", client)

    assert client.calls == 1


def test_write_tools_are_never_retried():
    client = FakeClient(failures=5)

    with pytest.raises(RuntimeError):
        run("create_pull_request", client)

    assert client.calls == 1


def test_native_tools_are_not_retried():
    calls = []

    class Native:
        name = "search_memory"
        description = "d"
        parameters = {"type": "object", "properties": {}}
        plugin_name = None

        def execute(self, **kwargs):
            calls.append(1)
            raise RuntimeError(GENERIC)

    registry = ToolRegistry()
    registry.register(Native())
    executor = ToolExecutor(registry, ToolContext(db=None, workspace_id=1, user_id=1))

    with pytest.raises(RuntimeError):
        executor.execute("search_memory", {})

    assert len(calls) == 1


# ---------------- prewarm ----------------

def test_warm_up_is_throttled_per_user():
    prewarm._LAST.clear()

    assert prewarm.should_warm(1, now=100.0)
    assert not prewarm.should_warm(1, now=150.0)
    assert prewarm.should_warm(2, now=150.0)
    assert prewarm.should_warm(1, now=100.0 + prewarm.MIN_INTERVAL + 1)


class FakeManager:
    def __init__(self, fail=False):
        self.fail = fail
        self.users = []

    async def connect_github(self, db, user_id, registry):
        self.users.append(user_id)

        if self.fail:
            raise RuntimeError("boom")

        return 45


class FakeSession:
    closed = False

    def close(self):
        FakeSession.closed = True


def patch_runtime(monkeypatch, manager):
    import app.db.session as session_mod
    import app.mcp.runtime as runtime_mod

    FakeSession.closed = False
    monkeypatch.setattr(runtime_mod, "mcp_integration_manager", manager)
    monkeypatch.setattr(session_mod, "SessionLocal", FakeSession)
    prewarm._LAST.clear()


def test_warm_up_connects_once_and_closes_its_session(monkeypatch, capsys):
    manager = FakeManager()
    patch_runtime(monkeypatch, manager)

    prewarm.warm_github(7)
    prewarm.warm_github(7)

    assert manager.users == [7]
    assert FakeSession.closed
    assert "GitHub MCP warmed up" in capsys.readouterr().out


def test_a_failed_warm_up_never_raises_and_allows_a_retry(monkeypatch):
    manager = FakeManager(fail=True)
    patch_runtime(monkeypatch, manager)

    prewarm.warm_github(7)
    prewarm.warm_github(7)

    assert manager.users == [7, 7]
    assert FakeSession.closed


def status_client(monkeypatch, connected):
    warmed = []

    monkeypatch.setattr(
        oauth_routes, "get_user_integration",
        lambda **kwargs: object() if connected else None,
    )
    monkeypatch.setattr(oauth_routes, "warm_github", lambda user_id: warmed.append(user_id))

    app = FastAPI()
    app.include_router(oauth_routes.router)
    app.dependency_overrides[get_db] = lambda: None
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=7)

    return TestClient(app), warmed


def test_status_call_starts_the_warm_up_when_github_is_connected(monkeypatch):
    client, warmed = status_client(monkeypatch, connected=True)
    response = client.get("/oauth/github/status")

    assert response.json() == {"connected": True}
    assert warmed == [7]


def test_status_call_does_not_warm_up_without_a_connection(monkeypatch):
    client, warmed = status_client(monkeypatch, connected=False)
    response = client.get("/oauth/github/status")

    assert response.json() == {"connected": False}
    assert warmed == []
