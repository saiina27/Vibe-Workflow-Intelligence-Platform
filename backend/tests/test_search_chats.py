import importlib
import pkgutil
from datetime import datetime
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.models

for _m in pkgutil.iter_modules(app.models.__path__):
    importlib.import_module(f"app.models.{_m.name}")

from app.ai.prompt_builder import build_prompt
from app.ai.tools import chat_search_tool as cst
from app.ai.tools.chat_search_tool import ChatSearchTool, _snippet
from app.ai.tools.context import ToolContext
from app.ai.tools.registry import ToolRegistry
from app.db.base import Base
from app.models.chat import Chat
from app.models.message import Message
from app.repositories.message_repository import search_messages


# ---------------- repository (real SQL on SQLite) ----------------

@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(
        engine, tables=[Chat.__table__, Message.__table__]
    )
    session = sessionmaker(bind=engine)()

    session.add_all([
        Chat(id=1, workspace_id=1, title="Auth chat"),
        Chat(id=2, workspace_id=1, title="Other chat"),
        Chat(id=3, workspace_id=2, title="Foreign workspace"),
    ])
    session.flush()

    def msg(i, chat, role, text, when):
        return Message(
            id=i, chat_id=chat, role=role, content=text, created_at=when
        )

    session.add_all([
        msg(1, 1, "user", "JWT refresh token discussion", datetime(2026, 10, 4, 20, 0)),
        msg(2, 1, "assistant", "Use short-lived access tokens", datetime(2026, 10, 4, 20, 1)),
        msg(3, 2, "user", "unrelated topic", datetime(2026, 10, 1, 10, 0)),
        msg(4, 3, "user", "JWT secret in another workspace", datetime(2026, 10, 4, 20, 0)),
        msg(5, 1, "system", "JWT hidden system text", datetime(2026, 10, 4, 20, 2)),
    ])
    session.commit()

    yield session
    session.close()


def ids(rows):
    return {m.id for m, _ in rows}


def test_workspace_isolation_and_roles(db):
    found = ids(search_messages(db, 1, keywords=["jwt"]))
    assert found == {1}


def test_current_chat_excluded(db):
    found = ids(search_messages(db, 1, exclude_chat_id=1, keywords=["jwt"]))
    assert found == set()


def test_date_window(db):
    rows = search_messages(
        db, 1,
        start=datetime(2026, 10, 4),
        end=datetime(2026, 10, 5),
    )
    assert ids(rows) == {1, 2}


def test_limit_and_newest_first(db):
    rows = search_messages(db, 1, limit=1)
    assert [m.id for m, _ in rows] == [2]


def test_like_wildcards_are_escaped(db):
    assert search_messages(db, 1, keywords=["%"]) == []
    assert search_messages(db, 1, keywords=["_"]) == []


# ---------------- tool ----------------

def make_tool(monkeypatch, rows=None):
    captured = {}

    def fake(**kwargs):
        captured.update(kwargs)
        return rows or []

    monkeypatch.setattr(cst, "search_messages", fake)
    ctx = ToolContext(db=None, workspace_id=1, user_id=1, chat_id=7)
    return ChatSearchTool(ctx), captured


def test_date_is_converted_from_ist_to_utc(monkeypatch):
    tool, cap = make_tool(monkeypatch)
    out = tool.execute(date_from="2026-10-05")

    assert out["success"] is True
    assert cap["start"] == datetime(2026, 10, 4, 18, 30)
    assert cap["end"] == datetime(2026, 10, 5, 18, 30)
    assert cap["exclude_chat_id"] == 7
    assert cap["workspace_id"] == 1


def test_date_range_is_inclusive(monkeypatch):
    tool, cap = make_tool(monkeypatch)
    tool.execute(date_from="2026-10-05", date_to="2026-10-06")
    assert cap["end"] == datetime(2026, 10, 6, 18, 30)


def test_last_days(monkeypatch):
    tool, cap = make_tool(monkeypatch)
    tool.execute(last_days=7)
    assert cap["start"] is not None and cap["end"] is None


def test_bad_date_and_empty_args(monkeypatch):
    tool, _ = make_tool(monkeypatch)
    assert tool.execute(date_from="not-a-date")["success"] is False
    assert tool.execute()["success"] is False


def test_output_shape_and_extra_args_ignored(monkeypatch):
    message = SimpleNamespace(
        role="user",
        content="x" * 1000,
        created_at=datetime(2026, 10, 4, 20, 0),
    )
    chat = SimpleNamespace(id=3, title="Auth chat")
    tool, _ = make_tool(monkeypatch, rows=[(message, chat)])

    out = tool.execute(keywords="jwt", unexpected="ignored")

    item = out["messages"][0]
    assert item["time"] == "2026-10-05 01:30 IST"
    assert len(item["snippet"]) <= cst.SNIPPET_CHARS + 2
    assert out["count"] == 1


def test_snippet_centers_on_keyword():
    text = "a" * 500 + " needle " + "b" * 500
    assert "needle" in _snippet(text, ["needle"])


# ---------------- registry ----------------

class FakeTool:
    def __init__(self, name, plugin=None):
        self.name = name
        self.description = f"{name} tool"
        self.parameters = {"type": "object", "properties": {}}
        self.plugin_name = plugin


def exposed(text):
    prompt = build_prompt(
        memories=[], conversation_summary=None,
        history=[SimpleNamespace(role="user", content=text)],
        knowledge_chunks=[], include_memories=False,
        include_knowledge=False,
    )
    reg = ToolRegistry()
    for n in ("get_me", "list_commits", "list_pull_requests",
              "search_repositories", "create_pull_request"):
        reg.register(FakeTool(n, "github"))
    for n in ("search_web", "search_knowledge", "search_memory",
              "search_chats"):
        reg.register(FakeTool(n))
    return {d.name for d in reg.definitions_for_prompt(prompt)}


def test_non_github_question_gets_search_chats():
    assert "search_chats" in exposed("5 Oct wali chat mein humne kya kiya tha")


def test_github_question_has_no_search_chats_by_default():
    assert "search_chats" not in exposed("show the branches of my repo X")


def test_github_plus_chat_words_gets_search_chats():
    names = exposed("what did we discuss earlier in chat about my repo X commits")
    assert "search_chats" in names
    assert "create_pull_request" not in names


def test_prompt_mentions_search_chats():
    prompt = build_prompt(
        memories=[], conversation_summary=None,
        history=[SimpleNamespace(role="user", content="hi")],
        knowledge_chunks=[], include_memories=False,
        include_knowledge=False,
    )
    assert "search_chats" in prompt


def test_search_chats_optional_params_accept_null():
    tool = ChatSearchTool(ToolContext(db=None, workspace_id=1, user_id=1))
    props = tool.parameters["properties"]

    for key in ("keywords", "date_from", "date_to", "last_days"):
        assert "null" in props[key]["type"]


def test_prompt_contains_todays_date():
    from datetime import timedelta

    prompt = build_prompt(
        memories=[], conversation_summary=None,
        history=[SimpleNamespace(role="user", content="hi")],
        knowledge_chunks=[], include_memories=False,
        include_knowledge=False,
    )
    year = str((datetime.utcnow() + timedelta(hours=5, minutes=30)).year)

    assert "TODAY'S DATE (IST)" in prompt
    assert year in prompt


def test_null_arguments_are_handled(monkeypatch):
    tool, _ = make_tool(monkeypatch)
    out = tool.execute(
        keywords=["jwt"], date_from=None, date_to=None, last_days=None
    )
    assert out["success"] is True
