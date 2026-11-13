import importlib
import json
import pkgutil
from datetime import date, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models

for _m in pkgutil.iter_modules(app.models.__path__):
    importlib.import_module(f"app.models.{_m.name}")

from app.ai.prompt_builder import build_prompt
from app.ai.tools.registry import ToolRegistry
from app.api.routes import dev_events as routes
from app.db.base import Base
from app.dependencies.auth import get_current_user
from app.dependencies.database import get_db
from app.mcp.tool_adapter import MCPToolAdapter
from app.models.dev_event import DevEvent
from app.models.tracked_slack_term import TrackedSlackTerm
from app.models.workspace import Workspace
from app.services import dev_events_service as dev
from app.services import slack_sync_service as ss

NOW = datetime(2026, 11, 9, 12, 0)
TS1 = "1791294435.376399"

BLOCK = (
    "### Result {n} of {total}\n"
    "Channel: #dev-updates (ID: C0C7YC4CBT2)\n"
    "From: saiina27 (ID: U0BTS5XB1D0) \n"
    "Time: 2026-10-06 19:17:15 IST\n"
    "Message_ts: {ts}\n"
    "Permalink: [link](https://vibe-development.slack.com/archives/C0C7YC4CBT2/p{p})\n"
    "Text: \n{text}\n"
    "Context before: \n- From: (ID: U00) \n Message_ts: 1791294396.034029\n"
    " <@U0BTS5XB1D0|saiina27> has joined the channel\n"
    "Context after: \n- From: saiina27 (ID: U0BTS5XB1D0) \n Message_ts: 1791294476.060729\n"
    " We decided to use Groq as the fallback provider\n\n---\n\n"
)


def slack_text(*messages):
    body = f"# Search Results for: \n\n## Messages ({len(messages)} results)\n"

    for i, (ts, text) in enumerate(messages, 1):
        body += BLOCK.format(n=i, total=len(messages), ts=ts, p=ts.replace(".", ""), text=text)

    return json.dumps({"results": body, "pagination_info": "End of results"})


def fake_call(text, calls=None):
    def call(tool, arguments):
        if calls is not None:
            calls.append((tool, arguments))

        return {"content": [{"type": "text", "text": text}], "is_error": False}

    return call


# ---------------- parsing ----------------

def test_a_real_result_becomes_one_event():
    events = ss.parse_slack_results(slack_text((TS1, "Deployment failed on Render, checking logs")))

    assert len(events) == 1
    e = events[0]

    assert e["source"] == "slack" and e["event_type"] == "slack_message"
    assert e["repo"] == "#dev-updates" and e["author"] == "saiina27"
    assert e["external_id"] == f"C0C7YC4CBT2:{TS1}"
    assert e["url"] == "https://vibe-development.slack.com/archives/C0C7YC4CBT2/p1791294435376399"
    assert e["title"] == "Deployment failed on Render, checking logs"
    assert e["occurred_at"].date() == date(2026, 10, 6)


def test_context_messages_are_not_saved():
    text = json.dumps(ss.parse_slack_results(slack_text((TS1, "Hello team"))), default=str)

    assert "joined the channel" not in text and "fallback provider" not in text


def test_several_results_and_empty_results():
    events = ss.parse_slack_results(slack_text((TS1, "first"), ("1791294500.000100", "second")))

    assert [e["title"] for e in events] == ["first", "second"]
    assert ss.parse_slack_results(json.dumps({"results": "# Search Results for: \n\nNo results found.\n"})) == []
    assert ss.parse_slack_results("") == [] and ss.parse_slack_results("not json") == []


def test_the_time_line_is_the_fallback_for_the_timestamp():
    text = slack_text(("", "No timestamp"))
    event = ss.parse_slack_results(text)[0]

    assert event["occurred_at"] == datetime(2026, 10, 6, 13, 47, 15)


def test_slack_markup_is_cleaned_and_long_text_is_clipped():
    raw = "<@U0BTS5XB1D0|saiina27> see <https://x.test|the link> in <#C123|dev-updates> &amp; <@U1>"

    assert ss.clean_snippet(raw) == "@saiina27 see the link in #dev-updates & @user"

    clipped = ss.clean_snippet("word " * 100)
    assert len(clipped) <= ss.SNIPPET_CHARS and clipped.endswith("...")


# ---------------- watch words ----------------

@pytest.fixture
def engine():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(
        engine, tables=[Workspace.__table__, TrackedSlackTerm.__table__, DevEvent.__table__]
    )
    return engine


@pytest.fixture
def db(engine):
    session = sessionmaker(bind=engine)()
    workspace = Workspace(name="w", user_id=1)
    session.add(workspace)
    session.commit()
    session.wid = workspace.id

    yield session

    session.close()


def test_terms_are_cleaned_and_validated():
    assert ss.clean_term("  deploy   fail ") == "deploy fail"

    for bad in ("a", "", "x" * 61, "drop;table", "line\nbreak?"):
        with pytest.raises(ValueError):
            ss.clean_term(bad)


def test_adding_listing_and_deleting_terms(db):
    first = ss.add_term(db, db.wid, "deployment")
    ss.add_term(db, db.wid, "decided")

    assert [t.term for t in ss.list_terms(db, db.wid)] == ["decided", "deployment"]

    with pytest.raises(ValueError, match="already"):
        ss.add_term(db, db.wid, "DEPLOYMENT")

    assert ss.delete_term(db, db.wid, first.id) is True
    assert ss.delete_term(db, db.wid, first.id) is False


def test_the_number_of_terms_is_capped(db):
    for i in range(ss.MAX_TERMS):
        ss.add_term(db, db.wid, f"word{i}")

    with pytest.raises(ValueError, match="At most"):
        ss.add_term(db, db.wid, "oneMore")


# ---------------- sync ----------------

def test_syncing_a_term_saves_events_once(db):
    row = ss.add_term(db, db.wid, "deployment")
    calls = []
    call = fake_call(slack_text((TS1, "Deployment failed"), ("1791294500.000100", "Deployed again")), calls)

    first = ss.sync_term(db, db.wid, "deployment", call, row)
    second = ss.sync_term(db, db.wid, "deployment", call, row)

    assert (first["events"], first["new"]) == (2, 2)
    assert (second["new"], second["same"]) == (0, 2)
    assert db.query(DevEvent).count() == 2
    assert row.last_synced_at is not None

    tool, arguments = calls[0]
    assert tool == "slack_search_public"
    assert arguments["keywords"] == ["deployment"]
    assert arguments["response_format"] == "detailed" and arguments["limit"] == 20


def test_one_failing_word_does_not_stop_the_others(db):
    ss.add_term(db, db.wid, "broken")
    ss.add_term(db, db.wid, "works")

    def call(tool, arguments):
        if arguments["keywords"] == ["broken"]:
            raise RuntimeError("Slack said no")

        return {"content": [{"type": "text", "text": slack_text((TS1, "ok"))}], "is_error": False}

    results = {r["term"]: r for r in ss.sync_terms(db, db.wid, call)}

    assert "error" in results["broken"] and results["works"]["new"] == 1


def test_clearing_removes_slack_events_only(db):
    db.add(DevEvent(workspace_id=db.wid, source="github", repo="o/r", event_type="commit",
                    external_id="s", title="t", occurred_at=NOW))
    db.commit()

    ss.sync_term(db, db.wid, "x", fake_call(slack_text((TS1, "hello"))), None)

    assert ss.delete_slack_events(db, db.wid) == 1
    assert [e.source for e in db.query(DevEvent).all()] == ["github"]


# ---------------- auto-sync ----------------

def seed_terms(db):
    other = Workspace(name="other", user_id=2)
    db.add(other)
    db.commit()

    db.add_all([
        TrackedSlackTerm(workspace_id=db.wid, term="old", last_synced_at=NOW - timedelta(hours=30)),
        TrackedSlackTerm(workspace_id=db.wid, term="fresh", last_synced_at=NOW - timedelta(hours=1)),
        TrackedSlackTerm(workspace_id=other.id, term="theirs"),
    ])
    db.commit()


def test_only_stale_terms_of_this_user_are_chosen(db):
    seed_terms(db)

    targets = ss.stale_terms(db, 1, NOW)

    assert [(w, [t.term for t in terms]) for w, terms in targets] == [(db.wid, ["old"])]


def test_auto_sync_refreshes_stale_terms(db, monkeypatch, capsys):
    seed_terms(db)
    monkeypatch.setattr(
        "app.services.external_integration_service.get_user_integration",
        lambda **kw: object(),
    )

    results = ss.run_slack_auto_sync(
        db, 1, now=NOW,
        connect=lambda *a: None,
        make_call=lambda *a: fake_call(slack_text((TS1, "Deployment failed"))),
    )

    assert [r["term"] for r in results] == ["old"] and results[0]["new"] == 1
    assert "Slack auto-sync 'old': 1 messages (1 new)" in capsys.readouterr().out


def test_auto_sync_does_nothing_when_fresh_or_not_connected(db, monkeypatch, capsys):
    assert ss.run_slack_auto_sync(db, 1, now=NOW) == []
    assert "saved messages are fresh" in capsys.readouterr().out

    seed_terms(db)
    monkeypatch.setattr("app.services.external_integration_service.get_user_integration", lambda **kw: None)

    assert ss.run_slack_auto_sync(db, 1, now=NOW) == []
    assert "Slack is not connected" in capsys.readouterr().out


# ---------------- the caller is search-only ----------------

class FakeClient:
    def __init__(self):
        self.calls = []

    def call_tool(self, tool_name, arguments):
        self.calls.append(tool_name)
        return {"ok": True}


class AllowAll:
    def add_workspace_plugin(self, workspace_id, name):
        pass

    def is_tool_allowed(self, plugin_name, tool_name, context):
        return True


def test_the_slack_caller_allows_the_search_tool_only(monkeypatch):
    monkeypatch.setattr("app.mcp.runtime.mcp_permission_service", AllowAll())

    client = FakeClient()
    registry = ToolRegistry()

    for name in ("slack_search_public", "slack_send_message"):
        registry.register(MCPToolAdapter(
            client=client,
            tool=SimpleNamespace(name=name, description="d", input_schema={"type": "object", "properties": {}}),
            plugin_name="slack",
        ))

    call = ss._make_call(None, 5, 7, registry)

    assert call("slack_search_public", {}) == {"ok": True}

    with pytest.raises(PermissionError):
        call("slack_send_message", {})

    assert client.calls == ["slack_search_public"]


# ---------------- routes ----------------

@pytest.fixture
def client(engine, monkeypatch):
    monkeypatch.setattr(routes, "require_workspace_access", lambda **kw: None)
    Session = sessionmaker(bind=engine)

    def override():
        session = Session()

        try:
            yield session
        finally:
            session.close()

    app = FastAPI()
    app.include_router(routes.router)
    app.dependency_overrides[get_db] = override
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=7)

    client = TestClient(app)
    client.session = Session

    return client


def test_the_routes_add_list_and_remove_watch_words(client):
    added = client.post("/workspaces/1/slack-terms", json={"term": " deployment "})

    assert added.status_code == 200 and added.json()["term"] == "deployment"
    assert client.post("/workspaces/1/slack-terms", json={"term": "Deployment"}).status_code == 400
    assert client.post("/workspaces/1/slack-terms", json={"term": "a"}).status_code == 400
    assert [t["term"] for t in client.get("/workspaces/1/slack-terms").json()] == ["deployment"]

    term_id = added.json()["id"]

    assert client.delete(f"/workspaces/1/slack-terms/{term_id}").json() == {"deleted": True}
    assert client.delete(f"/workspaces/1/slack-terms/{term_id}").status_code == 404


def test_the_route_stops_at_the_term_limit(client):
    for i in range(ss.MAX_TERMS):
        assert client.post("/workspaces/1/slack-terms", json={"term": f"word{i}"}).status_code == 200

    assert client.post("/workspaces/1/slack-terms", json={"term": "extra"}).status_code == 400


def test_syncing_without_words_is_a_clear_error(client):
    response = client.post("/workspaces/1/slack-sync")

    assert response.status_code == 400 and "watch word" in response.json()["detail"]


def test_the_route_clears_saved_slack_messages(client):
    session = client.session()
    session.add_all([
        DevEvent(workspace_id=1, source="slack", repo="#a", event_type="slack_message",
                 external_id="1", title="t", occurred_at=NOW),
        DevEvent(workspace_id=1, source="github", repo="o/r", event_type="commit",
                 external_id="2", title="t", occurred_at=NOW),
    ])
    session.commit()
    session.close()

    assert client.delete("/workspaces/1/slack-events").json() == {"deleted": 1}


# ---------------- Slack tool schema ----------------

class FakeTool:
    def __init__(self, name, plugin, params):
        self.name = name
        self.description = f"{name} tool"
        self.parameters = {"type": "object", "properties": {p: {"type": "string"} for p in params}}
        self.plugin_name = plugin


def definitions(text, tools):
    registry = ToolRegistry()

    for tool in tools:
        registry.register(tool)

    prompt = build_prompt(
        [], None, [SimpleNamespace(role="user", content=text)], [], False, False
    )

    return {d.name: d for d in registry.definitions_for_prompt(prompt)}


def test_slack_optional_parameters_are_hidden_but_github_ones_are_not():
    slack = FakeTool(
        "slack_search_public", "slack",
        ["keywords", "limit", "content_types", "max_context_length", "context_channel_id",
         "cursor", "after", "before", "only_my_channels"],
    )

    defs = definitions("search Slack for deployment", [slack])
    assert set(defs["slack_search_public"].parameters["properties"]) == {"keywords", "limit"}

    github = FakeTool("list_commits", "github", ["owner", "repo", "after"])
    defs = definitions("show the latest commits of my repo X", [github])
    assert "after" in defs["list_commits"].parameters["properties"]


def test_slack_questions_get_the_short_answer_and_probably_related_rule():
    def prompt(text):
        return build_prompt([], None, [SimpleNamespace(role="user", content=text)], [], False, False)

    asked = prompt("what did the team say about deployment on Slack")

    assert "SLACK ANSWERS" in asked
    assert "probably related, never that one caused the other" in asked
    assert "SLACK ANSWERS" not in prompt("hi")
