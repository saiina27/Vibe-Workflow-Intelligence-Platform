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
from app.ai.tools.context import ToolContext
from app.ai.tools.history_search_tool import HistorySearchTool
from app.db.base import Base
from app.models.dev_event import DevEvent
from app.models.tracked_repo import TrackedRepo
from app.services import digest_service

ROWS = [
    (1, datetime(2026, 10, 6, 5, 0)),
    (1, datetime(2026, 10, 6, 6, 0)),
    (2, datetime(2026, 10, 6, 7, 0)),
    (9, datetime(2026, 10, 6, 8, 0)),   # the chat that is asking
    (3, datetime(2026, 10, 7, 5, 0)),   # the next IST day
]
CHATS = {
    1: ("Same title", "DevOps"),
    2: ("Same title", "DevOps"),
    3: ("Later chat", None),
    9: ("Asking chat", None),
}


@pytest.fixture
def tool(monkeypatch):
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine, tables=[DevEvent.__table__, TrackedRepo.__table__])
    session = sessionmaker(bind=engine)()

    session.add(DevEvent(
        workspace_id=1, source="github", repo="o/r", event_type="commit",
        external_id="a", title="Routing work", occurred_at=datetime(2026, 10, 6, 5, 0),
    ))
    session.commit()

    monkeypatch.setattr(
        digest_service, "fetch_chat_activity",
        lambda db, workspace_id, start: {"rows": ROWS, "chats": CHATS},
    )

    yield HistorySearchTool(ToolContext(db=session, workspace_id=1, user_id=1, chat_id=9))

    session.close()


def test_a_date_question_also_lists_the_chats_of_that_day(tool):
    out = tool.execute(date_from="2026-10-06")

    assert out["count"] == 1
    assert out["chats"] == [{"title": "Same title", "questions": 3}]


def test_the_asking_chat_and_other_days_are_left_out(tool):
    titles = [c["title"] for c in tool.execute(date_from="2026-10-06")["chats"]]

    assert "Asking chat" not in titles and "Later chat" not in titles


def test_a_relative_period_lists_chats_too(tool):
    out = tool.execute(last_days=30)

    assert {c["title"] for c in out["chats"]} >= {"Same title"}


def test_keywords_a_type_or_a_repo_leave_the_chats_out(tool):
    assert "chats" not in tool.execute(date_from="2026-10-06", keywords=["routing"])
    assert "chats" not in tool.execute(date_from="2026-10-06", event_type="commit")
    assert "chats" not in tool.execute(date_from="2026-10-06", repo="o/r")


def test_without_a_period_no_chat_lookup_happens(tool, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("must not look up chats")

    monkeypatch.setattr(digest_service, "fetch_chat_activity", forbidden)

    assert "chats" not in tool.execute()


def test_a_failing_chat_lookup_never_breaks_the_answer(tool, monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("database error")

    monkeypatch.setattr(digest_service, "fetch_chat_activity", boom)

    out = tool.execute(date_from="2026-10-06")

    assert out["success"] is True and out["count"] == 1 and "chats" not in out


def test_the_prompt_asks_for_all_types_on_a_broad_date_question():
    prompt = build_prompt(
        [], None,
        [SimpleNamespace(role="user", content="what happened on 6 Oct")],
        [], False, False,
    )

    assert 'broad "what happened on <date>" question leave event_type' in prompt
    assert "add one line about the chats in the result" in prompt
