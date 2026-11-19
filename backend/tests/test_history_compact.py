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


def make_tool(monkeypatch, commits):
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine, tables=[DevEvent.__table__, TrackedRepo.__table__])
    session = sessionmaker(bind=engine)()

    for i in range(commits):
        session.add(DevEvent(
            workspace_id=1, source="github", repo="o/vibe", event_type="commit",
            external_id=f"c{i}", title=f"Work number {i}", author="saiina27",
            url=f"https://github.com/o/vibe/commit/{i}", occurred_at=datetime(2026, 10, 6, 4 + i % 6, i),
        ))

    session.add(DevEvent(
        workspace_id=1, source="github", repo="o/vibe", event_type="pull_request",
        external_id="p1", title="Add check", author="saiina27", detail="closed",
        url="https://github.com/o/vibe/pull/1", occurred_at=datetime(2026, 10, 6, 7, 0),
    ))
    session.add(DevEvent(
        workspace_id=1, source="slack", repo="#dev-updates", event_type="slack_message",
        external_id="C1:1", title="Deployment failed", author="saiina27",
        url="https://x.slack.com/archives/C1/p1", occurred_at=datetime(2026, 10, 6, 8, 0),
    ))
    session.commit()

    monkeypatch.setattr(
        digest_service, "fetch_chat_activity",
        lambda db, workspace_id, start: {"rows": [], "chats": {}},
    )

    return HistorySearchTool(ToolContext(db=session, workspace_id=1, user_id=1))


def test_long_lists_get_short_rows_and_repeated_values_move_up(monkeypatch):
    out = make_tool(monkeypatch, commits=8).execute(date_from="2026-10-06")

    assert out["count"] == 10
    assert out["repo"] == "o/vibe" and out["author"] == "saiina27"
    assert out["time_zone"] == "IST"

    commit = next(e for e in out["events"] if e["type"] == "commit")
    assert set(commit) == {"type", "time", "title"}
    assert not commit["time"].endswith("IST")

    pr = next(e for e in out["events"] if e["type"] == "pull_request")
    assert pr["status"] == "closed" and "url" not in pr

    slack = next(e for e in out["events"] if e["type"] == "slack_message")
    assert slack["channel"] == "#dev-updates"
    assert slack["url"].startswith("https://x.slack.com")


def test_short_lists_keep_every_detail(monkeypatch):
    out = make_tool(monkeypatch, commits=2).execute(date_from="2026-10-06")

    assert out["count"] == 4
    assert "time_zone" not in out and "repo" not in out
    assert {"repo", "url", "author"} <= set(out["events"][0])


def test_a_long_list_is_much_smaller_than_before(monkeypatch):
    import json

    out = make_tool(monkeypatch, commits=12).execute(date_from="2026-10-06")

    assert len(json.dumps(out["events"])) < 2400


def prompt_for(text):
    return build_prompt(
        [], None, [SimpleNamespace(role="user", content=text)], [], False, False
    )


def test_decision_questions_get_the_vague_question_rule():
    for text in ("why did we choose Groq as the fallback provider", "why did we c"):
        assert "CUT-OFF OR VAGUE QUESTIONS" in prompt_for(text)

    assert "CUT-OFF OR VAGUE QUESTIONS" not in prompt_for("hi")


def test_improvement_questions_are_told_not_to_put_pipes_in_cells():
    prompt = prompt_for("how can I improve the router")

    assert "never put the | character inside a cell" in prompt
