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

from app.ai.prompt_builder import build_prompt
from app.ai.tools.context import ToolContext
from app.ai.tools.history_search_tool import HistorySearchTool
from app.ai.tools.registry import MAX_EXPOSED_TOOLS, ToolRegistry
from app.db.base import Base
from app.models.dev_event import DevEvent
from app.models.tracked_repo import TrackedRepo


def event(i, ws, kind, title, when, author="saiina27", repo="o/r", detail=None):
    return DevEvent(
        id=i, workspace_id=ws, source="github", repo=repo,
        event_type=kind, external_id=str(i), title=title,
        author=author, url=f"https://x/{i}", detail=detail,
        occurred_at=when,
    )


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(
        engine, tables=[TrackedRepo.__table__, DevEvent.__table__]
    )
    session = sessionmaker(bind=engine)()

    session.add_all([
        event(1, 1, "commit", "Add rate limiting", datetime(2026, 10, 5, 5, 0)),
        event(2, 1, "commit", "Late night fix", datetime(2026, 10, 5, 20, 0)),
        event(3, 1, "pull_request", "Auth refactor", datetime(2026, 10, 5, 6, 0), detail="closed"),
        event(4, 2, "commit", "Other workspace rate limiting", datetime(2026, 10, 5, 5, 0)),
        event(5, 1, "commit", "Other repo change", datetime(2026, 10, 5, 7, 0), repo="o/other"),
    ])
    session.commit()

    yield session
    session.close()


def tool(db, ws=1):
    return HistorySearchTool(ToolContext(db=db, workspace_id=ws, user_id=1))


def titles(out):
    return {e["title"] for e in out["events"]}


def test_ist_date_window(db):
    out = tool(db).execute(date_from="2026-10-05")

    # 20:00 UTC is already 6 Oct in IST, so it is excluded
    assert titles(out) == {"Add rate limiting", "Auth refactor", "Other repo change"}


def test_workspace_isolation(db):
    out = tool(db).execute(keywords=["rate"])
    assert titles(out) == {"Add rate limiting"}


def test_event_type_and_aliases(db):
    out = tool(db).execute(event_type="PRs")
    assert titles(out) == {"Auth refactor"}


def test_repo_filter_and_status(db):
    out = tool(db).execute(repo="other")
    assert titles(out) == {"Other repo change"}

    pr = tool(db).execute(event_type="pull_request")["events"][0]
    assert pr["status"] == "closed"


def test_output_has_ist_time_and_no_email_fields(db):
    item = tool(db).execute(keywords=["rate"])["events"][0]

    assert item["time"] == "2026-10-05 10:30 IST"
    assert set(item) == {"type", "repo", "time", "title", "author", "status", "url"}


def test_null_arguments_and_bad_dates(db):
    ok = tool(db).execute(
        keywords=None, date_from=None, date_to=None,
        last_days=None, event_type=None, repo=None,
    )
    assert ok["success"] is True

    assert tool(db).execute(date_from="nope")["success"] is False


def test_note_when_nothing_tracked_and_sync_time_when_tracked(db):
    assert "note" in tool(db).execute()

    db.add(TrackedRepo(
        workspace_id=1, full_name="o/r",
        last_synced_at=datetime(2026, 10, 8, 12, 0),
    ))
    db.commit()

    out = tool(db).execute()
    assert "note" not in out
    assert out["synced_through"] == "2026-10-08 17:30 IST"


def test_limit_is_respected(db):
    for i in range(100, 140):
        db.add(event(i, 1, "commit", f"bulk {i}", datetime(2026, 10, 6, 5, 0)))
    db.commit()

    out = tool(db).execute()
    assert out["count"] == 15 and out["may_have_more"] is True


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
    for n in ("get_me", "list_commits", "get_commit", "list_branches",
              "get_file_contents", "list_pull_requests",
              "search_repositories", "create_pull_request"):
        reg.register(FakeTool(n, "github"))
    for n in ("search_web", "search_knowledge", "search_memory",
              "search_chats", "search_history"):
        reg.register(FakeTool(n))
    return {d.name for d in reg.definitions_for_prompt(prompt)}


def test_non_github_question_gets_search_history():
    assert "search_history" in exposed("5 Oct ko kya hua tha")


def test_github_question_with_history_word_gets_it():
    names = exposed("show the commit history of my repo X")
    assert "search_history" in names
    assert "create_pull_request" not in names
    assert len(names) <= MAX_EXPOSED_TOOLS


def test_plain_github_question_has_no_history_tool():
    assert "search_history" not in exposed("show the branches of my repo X")


def test_prompt_mentions_search_history():
    prompt = build_prompt(
        memories=[], conversation_summary=None,
        history=[SimpleNamespace(role="user", content="hi")],
        knowledge_chunks=[], include_memories=False,
        include_knowledge=False,
    )
    assert "search_history" in prompt


def test_past_period_hides_live_list_tools_but_keeps_history():
    names = exposed("last week mein kaun se pull requests bane the")
    assert "search_history" in names
    assert "list_pull_requests" not in names
    assert "list_commits" not in names
    assert {"get_me", "search_repositories"} <= names


def test_date_in_question_uses_history_path():
    names = exposed("5 Oct ko mere repo ke commits kya the")
    assert "search_history" in names
    assert "list_commits" not in names

    iso = exposed("show commits of my repo X on 2026-10-05")
    assert "search_history" in iso and "list_commits" not in iso


def test_latest_questions_still_use_live_tools():
    names = exposed("show the latest commits of my repo X")
    assert "list_commits" in names
    assert "search_history" not in names


def test_commit_history_wording_keeps_live_tools():
    names = exposed("show the commit history of my repo X")
    assert "list_commits" in names
    assert "search_history" in names


def test_decision_word_is_not_a_date():
    assert "list_commits" in exposed("show the decision 2 commits of my repo X")


def test_history_prompt_rules():
    prompt = build_prompt(
        memories=[], conversation_summary=None,
        history=[SimpleNamespace(role="user", content="hi")],
        knowledge_chunks=[], include_memories=False,
        include_knowledge=False,
    )
    assert "never ask which" in prompt
    assert "owner:<username>" not in prompt


def test_prompt_has_no_angle_bracket_owner_placeholders():
    prompt = build_prompt(
        memories=[], conversation_summary=None,
        history=[SimpleNamespace(role="user", content="hi")],
        knowledge_chunks=[], include_memories=False,
        include_knowledge=False,
    )
    assert "owner:<" not in prompt


def test_existence_questions_use_history_and_hide_live_list_tools():
    for text in (
        "rate limiting ke baare mein koi commit hua tha kya",
        "was there ever a commit about rate limiting in my repo X",
    ):
        names = exposed(text)
        assert "search_history" in names
        assert "list_commits" not in names
        assert "list_pull_requests" not in names
        assert len(names) <= MAX_EXPOSED_TOOLS
        assert "create_pull_request" not in names


def test_prompt_forbids_nothing_found_from_shortened_lists():
    prompt = build_prompt(
        memories=[], conversation_summary=None,
        history=[SimpleNamespace(role="user", content="hi")],
        knowledge_chunks=[], include_memories=False,
        include_knowledge=False,
    )
    assert "shortened live list" in prompt


def test_short_followup_after_existence_question_keeps_history_path():
    prompt = build_prompt(
        memories=[], conversation_summary=None,
        history=[
            SimpleNamespace(role="user", content="rate limiting ke baare mein koi commit hua tha kya"),
            SimpleNamespace(role="assistant", content="Which repository?"),
            SimpleNamespace(role="user", content="vibe"),
        ],
        knowledge_chunks=[], include_memories=False,
        include_knowledge=False,
    )
    reg = ToolRegistry()
    for n in ("get_me", "list_commits", "list_pull_requests",
              "search_repositories", "create_pull_request"):
        reg.register(FakeTool(n, "github"))
    for n in ("search_web", "search_knowledge", "search_memory",
              "search_chats", "search_history"):
        reg.register(FakeTool(n))

    names = {d.name for d in reg.definitions_for_prompt(prompt)}
    assert "search_history" in names
    assert "list_commits" not in names


def test_live_words_keep_live_tools_even_with_existence_words():
    names = exposed("latest commit kya hua in my repo X")
    # Live tools stay visible. search_history may also be present
    # (extra, within the tool budget).
    assert "list_commits" in names
    assert len(names) <= MAX_EXPOSED_TOOLS
    assert "create_pull_request" not in names
