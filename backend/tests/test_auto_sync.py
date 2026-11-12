import importlib
import pkgutil
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.models

for _m in pkgutil.iter_modules(app.models.__path__):
    importlib.import_module(f"app.models.{_m.name}")

from app.ai.tools.registry import ToolRegistry
from app.db.base import Base
from app.mcp import prewarm
from app.mcp.tool_adapter import MCPToolAdapter
from app.models.tracked_repo import TrackedRepo
from app.models.workspace import Workspace
from app.services import auto_sync_service as svc
from app.services import dev_events_service as dev

NOW = datetime(2026, 11, 9, 12, 0)


@pytest.fixture(autouse=True)
def default_hours(monkeypatch):
    monkeypatch.delenv("AUTO_SYNC_HOURS", raising=False)


def repo(hours_ago):
    synced = None if hours_ago is None else NOW - timedelta(hours=hours_ago)
    return SimpleNamespace(last_synced_at=synced)


# ---------------- when is history stale ----------------

def test_never_synced_or_older_than_six_hours_is_stale():
    assert svc.is_stale(repo(None), NOW)
    assert svc.is_stale(repo(7), NOW)
    assert svc.is_stale(repo(6), NOW)
    assert not svc.is_stale(repo(5), NOW)


def test_the_limit_can_be_changed_or_switched_off(monkeypatch):
    monkeypatch.setenv("AUTO_SYNC_HOURS", "1")
    assert svc.is_stale(repo(2), NOW) and not svc.is_stale(repo(0.5), NOW)

    monkeypatch.setenv("AUTO_SYNC_HOURS", "0")
    assert not svc.is_stale(repo(None), NOW) and not svc.is_stale(repo(500), NOW)

    for bad in ("abc", "-3"):
        monkeypatch.setenv("AUTO_SYNC_HOURS", bad)
        assert svc.stale_after() == timedelta(hours=6)


# ---------------- which repos ----------------

@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine, tables=[Workspace.__table__, TrackedRepo.__table__])
    session = sessionmaker(bind=engine)()

    w1 = Workspace(name="one", user_id=1)
    w2 = Workspace(name="two", user_id=1)
    w3 = Workspace(name="other user", user_id=2)
    session.add_all([w1, w2, w3])
    session.commit()

    session.add_all([
        TrackedRepo(workspace_id=w1.id, full_name="a/stale"),
        TrackedRepo(workspace_id=w1.id, full_name="a/fresh", last_synced_at=NOW - timedelta(hours=1)),
        TrackedRepo(workspace_id=w1.id, full_name="a/old", last_synced_at=NOW - timedelta(hours=30)),
        TrackedRepo(workspace_id=w2.id, full_name="b/fresh", last_synced_at=NOW - timedelta(hours=2)),
        TrackedRepo(workspace_id=w3.id, full_name="c/stale"),
    ])
    session.commit()

    session.ids = (w1.id, w2.id, w3.id)

    yield session

    session.close()


def names(targets):
    return [(wid, sorted(r.full_name for r in repos)) for wid, repos in targets]


def test_only_stale_repos_of_this_users_workspaces_are_chosen(db):
    w1, _w2, _w3 = db.ids

    assert names(svc.stale_targets(db, 1, NOW)) == [(w1, ["a/old", "a/stale"])]
    assert names(svc.stale_targets(db, 99, NOW)) == []


# ---------------- running the sync ----------------

def test_stale_repos_are_synced_and_fresh_ones_are_left_alone(db, monkeypatch, capsys):
    synced = []

    def fake_sync(db_, workspace_id, full_name, call, tracked=None):
        synced.append((workspace_id, full_name))
        return {"repo": full_name, "events": 3, "new": 1, "updated": 0, "same": 2}

    monkeypatch.setattr(dev, "sync_repo", fake_sync)

    results = svc.run_auto_sync(
        db, 1, registry=None, now=NOW,
        make_call=lambda *args: (lambda tool, arguments: None),
    )

    assert sorted(n for _w, n in synced) == ["a/old", "a/stale"]
    assert len(results) == 2
    assert "Auto-sync a/stale: 3 events (1 new)" in capsys.readouterr().out


def test_one_failing_repo_does_not_stop_the_others(db, monkeypatch, capsys):
    def fake_sync(db_, workspace_id, full_name, call, tracked=None):
        if full_name == "a/old":
            raise RuntimeError("GitHub said no")

        return {"repo": full_name, "events": 1, "new": 1}

    monkeypatch.setattr(dev, "sync_repo", fake_sync)

    results = svc.run_auto_sync(
        db, 1, registry=None, now=NOW,
        make_call=lambda *args: (lambda tool, arguments: None),
    )

    assert {r["repo"] for r in results} == {"a/old", "a/stale"}
    assert [r for r in results if "error" in r][0]["repo"] == "a/old"
    assert "Auto-sync failed for a/old" in capsys.readouterr().out


def test_fresh_history_prints_one_line_and_calls_nothing(db, monkeypatch, capsys):
    monkeypatch.setenv("AUTO_SYNC_HOURS", "0")

    def forbidden(*args, **kwargs):
        raise AssertionError("must not sync")

    monkeypatch.setattr(dev, "sync_repo", forbidden)

    assert svc.run_auto_sync(db, 1, registry=None, now=NOW) == []
    assert "saved history is fresh" in capsys.readouterr().out


# ---------------- the caller is read-only ----------------

class FakeClient:
    def __init__(self):
        self.calls = []

    def call_tool(self, tool_name, arguments):
        self.calls.append(tool_name)
        return {"ok": True}


class AllowAll:
    def __init__(self):
        self.plugins = []

    def add_workspace_plugin(self, workspace_id, name):
        self.plugins.append((workspace_id, name))

    def is_tool_allowed(self, plugin_name, tool_name, context):
        return True


def test_the_caller_allows_only_the_sync_tools(monkeypatch):
    perms = AllowAll()
    monkeypatch.setattr("app.mcp.runtime.mcp_permission_service", perms)

    client = FakeClient()
    registry = ToolRegistry()

    for name in ("list_commits", "create_pull_request"):
        registry.register(MCPToolAdapter(
            client=client,
            tool=SimpleNamespace(name=name, description="d", input_schema={"type": "object", "properties": {}}),
            plugin_name="github",
        ))

    call = svc._make_call(None, 5, 7, registry)

    assert call("list_commits", {}) == {"ok": True}

    with pytest.raises(PermissionError):
        call("create_pull_request", {})

    assert client.calls == ["list_commits"]
    assert perms.plugins == [(5, "github")]


# ---------------- prewarm runs it ----------------

class FakeManager:
    def __init__(self):
        self.users = []

    async def connect_github(self, db, user_id, registry):
        self.users.append(user_id)
        return 45


class FakeSession:
    closed = False

    def close(self):
        FakeSession.closed = True

    def rollback(self):
        pass


def patch_runtime(monkeypatch):
    manager = FakeManager()

    monkeypatch.setattr("app.mcp.runtime.mcp_integration_manager", manager)
    monkeypatch.setattr("app.db.session.SessionLocal", FakeSession)
    prewarm._LAST.clear()
    FakeSession.closed = False

    return manager


def test_the_warm_up_runs_the_auto_sync_with_the_connected_registry(monkeypatch):
    manager = patch_runtime(monkeypatch)
    seen = []

    monkeypatch.setattr(
        svc, "run_auto_sync",
        lambda db, user_id, registry: seen.append((user_id, type(registry).__name__)),
    )

    prewarm.warm_github(7)

    assert manager.users == [7]
    assert seen == [(7, "ToolRegistry")]
    assert FakeSession.closed


def test_a_failing_auto_sync_never_breaks_the_warm_up(monkeypatch, capsys):
    manager = patch_runtime(monkeypatch)

    def boom(db, user_id, registry):
        raise RuntimeError("boom")

    monkeypatch.setattr(svc, "run_auto_sync", boom)

    prewarm.warm_github(7)
    out = capsys.readouterr().out

    assert manager.users == [7]
    assert "GitHub MCP warmed up" in out
    assert "Auto-sync skipped: boom" in out
    assert FakeSession.closed
