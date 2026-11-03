import asyncio
import inspect
import threading
import time
from types import SimpleNamespace

import pytest

from app.ai.gateway import AIGateway
from app.ai.mcp_status import (
    GITHUB_DOWN_MESSAGE,
    GITHUB_DOWN_NOTE,
    add_github_down_note,
    github_unavailable,
    only_core_tools,
)
from app.ai.prompt_builder import build_prompt
from app.ai.tools import router as router_mod
from app.ai.tools.context import ToolContext
from app.ai.tools.registry import ToolRegistry
from app.mcp import server_manager as sm
from app.services import external_integration_service as eis


# ---------------- server manager ----------------

class FakeClient:
    def __init__(self):
        self.connected = True
        self.closed = False

    def connect_http(self, url, access_token=None):
        self.connected = True

    def is_connected(self):
        return self.connected

    def close(self):
        self.closed = True
        self.connected = False


def manager_with(monkeypatch, factory=FakeClient):
    monkeypatch.setattr(sm, "MCPClient", factory)

    manager = sm.MCPServerManager()
    manager.register_server(
        sm.MCPServerConfig(name="g", transport="streamable_http", url="https://x.test/mcp")
    )

    return manager


def test_a_healthy_client_is_reused(monkeypatch):
    manager = manager_with(monkeypatch)
    first = asyncio.run(manager.connect("g", "token"))
    second = asyncio.run(manager.connect("g", "token"))

    assert first is second and not first.closed


def test_a_dead_client_is_closed_and_replaced(monkeypatch):
    manager = manager_with(monkeypatch)

    dead = FakeClient()
    dead.connected = False
    manager._clients["g"] = dead

    fresh = asyncio.run(manager.connect("g", "token"))

    assert fresh is not dead and dead.closed and fresh.connected
    assert manager._clients["g"] is fresh


def test_is_connected_may_be_a_property_or_missing(monkeypatch):
    class AsProperty:
        is_connected = False

        def close(self):
            pass

    assert sm.MCPServerManager._is_alive(AsProperty()) is False
    assert sm.MCPServerManager._is_alive(SimpleNamespace()) is True

    class Broken:
        def is_connected(self):
            raise RuntimeError("x")

    assert sm.MCPServerManager._is_alive(Broken()) is True


def test_parallel_connects_create_one_client(monkeypatch):
    created = []

    class Slow(FakeClient):
        def connect_http(self, url, access_token=None):
            time.sleep(0.15)
            super().connect_http(url, access_token)

    def make():
        client = Slow()
        created.append(client)
        return client

    manager = manager_with(monkeypatch, make)
    results = []

    def worker():
        results.append(asyncio.run(manager.connect("g", "token")))

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(created) == 1 and len({id(r) for r in results}) == 1


# ---------------- router retry ----------------

class FlakyManager:
    def __init__(self, fail_times):
        self.fail_times = fail_times
        self.connects = 0
        self.disconnects = []

    async def connect_github(self, db, user_id, registry):
        self.connects += 1

        if self.connects <= self.fail_times:
            raise RuntimeError("Server returned an error response")

        return 45

    async def connect_slack(self, db, user_id, registry):
        return 3

    async def disconnect_github(self, user_id):
        self.disconnects.append(("github", user_id))


class FakePermissions:
    def add_workspace_plugin(self, workspace_id, name):
        pass


def prompt_for(text):
    return build_prompt(
        memories=[], conversation_summary=None,
        history=[SimpleNamespace(role="user", content=text)],
        knowledge_chunks=[], include_memories=False, include_knowledge=False,
    )


def build(monkeypatch, fail_times):
    async def no_sleep(seconds):
        return None

    monkeypatch.setattr(router_mod.asyncio, "sleep", no_sleep)
    monkeypatch.setattr(router_mod, "mcp_permission_service", FakePermissions())
    monkeypatch.setattr(eis, "get_user_integration", lambda **kwargs: object())

    manager = FlakyManager(fail_times)
    router = router_mod.ToolRouter()
    router.mcp_integration_manager = manager

    context = ToolContext(
        db=None, workspace_id=1, user_id=7,
        allowed_tools=frozenset({"github", "slack"}),
    )

    asyncio.run(router.build_registry(context, prompt_for("show the latest commits of my repo X")))

    return manager


def test_one_failed_connect_is_retried_after_dropping_the_connection(monkeypatch):
    manager = build(monkeypatch, fail_times=1)

    assert manager.connects == 2
    assert manager.disconnects == [("github", 7)]


def test_a_working_connect_is_not_retried(monkeypatch):
    manager = build(monkeypatch, fail_times=0)

    assert manager.connects == 1 and manager.disconnects == []


def test_two_failures_are_not_retried_forever(monkeypatch):
    manager = build(monkeypatch, fail_times=5)

    assert manager.connects == 2
    assert len(manager.disconnects) == 2


# ---------------- GitHub down ----------------

class FakeTool:
    def __init__(self, name, plugin=None):
        self.name = name
        self.description = f"{name} tool"
        self.parameters = {"type": "object", "properties": {}}
        self.plugin_name = plugin


def registry_with(*tools):
    registry = ToolRegistry()

    for name, plugin in tools:
        registry.register(FakeTool(name, plugin))

    return registry


def test_github_question_without_github_tools_is_detected():
    down = registry_with(("search_memory", None), ("search_web", None))
    up = registry_with(("search_memory", None), ("list_commits", "github"))

    prompt = prompt_for("show the latest commits of my repo X")

    assert github_unavailable(prompt, down)
    assert not github_unavailable(prompt, up)


def test_other_questions_are_never_blocked_by_missing_github():
    down = registry_with(("search_memory", None))

    assert not github_unavailable(prompt_for("hi"), down)
    assert not github_unavailable(prompt_for("summarize my uploaded PDF"), down)
    assert not github_unavailable(prompt_for("search Slack for deployment"), down)


def test_only_the_general_tools_count_as_nothing_useful_left():
    assert only_core_tools({"search_memory", "search_web"})
    assert not only_core_tools({"search_memory", "find_in_code"})
    assert not only_core_tools({"search_history"})


def test_the_note_goes_above_the_conversation_not_into_the_users_message():
    prompt = prompt_for("show the latest commits of my repo X")
    noted = add_github_down_note(prompt)

    assert noted.index(GITHUB_DOWN_NOTE) < noted.index("CURRENT CONVERSATION")
    assert ToolRegistry._latest_user_text(noted) == ToolRegistry._latest_user_text(prompt)
    assert ToolRegistry.mcp_needs(noted) == ToolRegistry.mcp_needs(prompt)


def test_message_tells_the_user_what_to_do():
    assert "GitHub button" in GITHUB_DOWN_MESSAGE
    assert "try again" in GITHUB_DOWN_MESSAGE


def test_the_gateway_uses_the_check_before_calling_the_model():
    source = inspect.getsource(AIGateway.stream_with_tools)

    assert "github_unavailable" in source
    assert source.index("github_unavailable") < source.index("_stream_provider_with_tools")
