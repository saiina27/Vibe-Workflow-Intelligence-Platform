import importlib
import pkgutil
from datetime import date, datetime
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.models

for _m in pkgutil.iter_modules(app.models.__path__):
    importlib.import_module(f"app.models.{_m.name}")

from app.api.routes import dev_events as routes
from app.db.base import Base
from app.dependencies.auth import get_current_user
from app.dependencies.database import get_db
from app.models.dev_event import DevEvent
from app.models.tracked_repo import TrackedRepo
from app.services import digest_service as ds

NOW = datetime(2026, 11, 3, 10, 0)  # 15:30 IST on 3 Nov


def commit(day, hour, title="Fix routing", sha="a" * 40, repo="o/vibe", author="Saina"):
    return {
        "type": "commit", "repo": repo, "title": title, "author": author,
        "detail": None, "external_id": sha, "at": datetime(2026, 11, day, hour, 0),
    }


def pull_request(day, title="Add check", state="closed"):
    return {
        "type": "pull_request", "repo": "o/vibe", "title": title, "author": "Saina",
        "detail": state, "external_id": "1", "at": datetime(2026, 11, day, 6, 0),
    }


def build(events=(), decisions=(), rows=(), chats=None, synced=None, days=7, notes=None):
    _, first, last = ds.period_bounds(days, NOW)
    data = ds.assemble(
        list(events), list(decisions),
        {"rows": list(rows), "chats": chats or {}}, synced, first, last, notes or [],
    )
    return data, ds.render_markdown(data)


# ---------------- period ----------------

def test_today_starts_at_ist_midnight():
    start, first, last = ds.period_bounds(1, NOW)

    assert first == last == date(2026, 11, 3)
    assert start == datetime(2026, 11, 2, 18, 30)


def test_a_week_has_seven_ist_days():
    _, first, last = ds.period_bounds(7, NOW)

    assert (first, last) == (date(2026, 10, 28), date(2026, 11, 3))


def test_days_are_clamped_and_bad_input_means_a_week():
    assert ds.clamp_days(0) == 1
    assert ds.clamp_days(500) == ds.MAX_DAYS
    assert ds.clamp_days("abc") == 7
    assert ds.clamp_days(None) == 7


def test_a_late_utc_evening_belongs_to_the_next_ist_day():
    assert ds.ist_day(datetime(2026, 11, 3, 18, 45)) == date(2026, 11, 4)
    assert ds.ist_day(datetime(2026, 11, 3, 18, 15)) == date(2026, 11, 3)


# ---------------- writing ----------------

def test_days_come_newest_first_with_counts_and_short_shas():
    data, text = build(
        events=[commit(3, 4, sha="abcdef1234567"), commit(2, 4, title="Older work"), pull_request(3)],
        decisions=[{"title": "Decision: Redis", "content": "Decision: Use Redis. Reason: fast.",
                    "at": datetime(2026, 11, 3, 5, 0)}],
        rows=[(1, datetime(2026, 11, 3, 5, 0)), (1, datetime(2026, 11, 3, 6, 0)), (2, datetime(2026, 11, 2, 5, 0))],
        chats={1: ("Latest commits", "Backend Development"), 2: ("Old chat", None)},
        synced=datetime(2026, 11, 3, 8, 50),
    )

    assert data["counts"] == {"commits": 2, "pull_requests": 1, "decisions": 1, "chats": 2, "questions": 3}
    assert text.index("## 03 Nov 2026") < text.index("## 02 Nov 2026")
    assert "`abcdef1`" in text and "abcdef12" not in text
    assert "- Add check (closed) by Saina" in text
    assert "- Decision: Use Redis. Reason: fast." in text
    assert "- Latest commits [Backend Development]: 2 questions" in text
    assert "last sync (03 Nov 2026 14:20 IST)" in text


def test_without_a_sync_the_digest_says_so():
    _, text = build(events=[], synced=None)

    assert "has not been synced yet" in text
    assert "No activity found in this period" in text


def test_long_days_are_capped_with_a_count_of_the_rest():
    events = [commit(3, 1, title=f"Work {i}") for i in range(ds.MAX_COMMITS_PER_DAY + 4)]
    _, text = build(events=events)

    assert "**Commits (12)**" in text
    assert "- ...and 4 more" in text
    assert text.count("- `") == ds.MAX_COMMITS_PER_DAY


def test_events_outside_the_period_are_ignored():
    data, _ = build(events=[commit(3, 4)], days=1)
    outside, _ = build(events=[dict(commit(3, 4), at=datetime(2026, 10, 1, 4, 0))], days=7)

    assert data["counts"]["commits"] == 1 and outside["counts"]["commits"] == 0


def test_the_repo_name_appears_only_when_there_are_several():
    _, one = build(events=[commit(3, 4)])
    _, two = build(events=[commit(3, 4), commit(3, 5, repo="o/other")])

    assert "[vibe]" not in one
    assert "[vibe]" in two and "[other]" in two


def test_titles_and_decisions_are_clipped_and_single_line():
    text = build(
        events=[commit(3, 4, title="x" * 400)],
        decisions=[{"title": "t", "content": "line one\nline two " + "y" * 500, "at": datetime(2026, 11, 3, 5, 0)}],
    )[1]

    assert "x" * 117 + "..." in text and "x" * 118 not in text
    assert "line one line two" in text


def test_the_markdown_has_a_size_cap():
    events = [commit(3, 1, title="z" * 110, sha=f"{i:040x}") for i in range(5)]
    decisions = [
        {"title": "t", "content": "d" * 290, "at": datetime(2026, 11, 1 + (i % 3), 5, 0)}
        for i in range(200)
    ]
    _, text = build(events=events, decisions=decisions, days=7)

    assert len(text) <= ds.MAX_MARKDOWN_CHARS + 200


# ---------------- build_digest ----------------

class FakeDb:
    rolled = 0

    def rollback(self):
        FakeDb.rolled += 1


def test_a_failing_section_is_noted_and_the_rest_still_works(monkeypatch):
    FakeDb.rolled = 0

    def broken(*args):
        raise RuntimeError("database error")

    monkeypatch.setattr(ds, "fetch_events", lambda db, ws, start: [commit(3, 4)])
    monkeypatch.setattr(ds, "fetch_decisions", lambda db, ws, start: [])
    monkeypatch.setattr(ds, "fetch_chat_activity", broken)
    monkeypatch.setattr(ds, "synced_through", lambda db, ws: datetime(2026, 11, 3, 8, 0))

    out = ds.build_digest(FakeDb(), 5, 7, now_utc=NOW)

    assert out["counts"]["commits"] == 1
    assert out["notes"] == ["Chats could not be loaded."]
    assert "Note: Chats could not be loaded." in out["markdown"]
    assert FakeDb.rolled == 1
    assert out["synced_through"] == "2026-11-03T08:00:00"
    assert out["days"] == 7


# ---------------- real queries on SQLite ----------------

@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine, tables=[DevEvent.__table__, TrackedRepo.__table__])
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


def add_event(db, ws, when, ext="s1", repo="o/vibe"):
    db.add(DevEvent(
        workspace_id=ws, source="github", repo=repo, event_type="commit",
        external_id=ext, title="t", occurred_at=when,
    ))


def test_events_are_scoped_to_the_workspace_and_the_period(db):
    start, _, _ = ds.period_bounds(7, NOW)

    add_event(db, 1, datetime(2026, 11, 3, 4, 0), "in")
    add_event(db, 1, datetime(2026, 10, 1, 4, 0), "old")
    add_event(db, 2, datetime(2026, 11, 3, 4, 0), "other")
    db.commit()

    assert [e["external_id"] for e in ds.fetch_events(db, 1, start)] == ["in"]


def test_synced_through_is_the_latest_sync_of_the_workspace(db):
    db.add_all([
        TrackedRepo(workspace_id=1, full_name="a/one", last_synced_at=datetime(2026, 11, 1, 1, 0)),
        TrackedRepo(workspace_id=1, full_name="a/two", last_synced_at=datetime(2026, 11, 3, 1, 0)),
        TrackedRepo(workspace_id=1, full_name="a/three"),
        TrackedRepo(workspace_id=2, full_name="b/x", last_synced_at=datetime(2026, 12, 1, 1, 0)),
    ])
    db.commit()

    assert ds.synced_through(db, 1) == datetime(2026, 11, 3, 1, 0)
    assert ds.synced_through(db, 9) is None


# ---------------- the endpoint ----------------

def test_the_endpoint_checks_access_and_returns_the_digest(monkeypatch):
    seen = {}

    monkeypatch.setattr(routes, "require_workspace_access", lambda **kw: seen.update(kw))
    monkeypatch.setattr(
        routes.digest_service, "build_digest",
        lambda db, workspace_id, days: {"markdown": f"digest {workspace_id} {days}"},
    )

    app = FastAPI()
    app.include_router(routes.router)
    app.dependency_overrides[get_db] = lambda: None
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=7)

    response = TestClient(app).get("/workspaces/5/digest?days=30")

    assert response.status_code == 200
    assert response.json() == {"markdown": "digest 5 30"}
    assert seen["workspace_id"] == 5 and seen["user_id"] == 7


def test_a_huge_digest_is_cut_at_the_cap_with_a_note(monkeypatch):
    monkeypatch.setattr(ds, "MAX_MARKDOWN_CHARS", 800)

    events = [commit(3, 1, title="z" * 110, sha=f"{i:040x}") for i in range(8)]
    _, text = build(events=events, days=7)

    assert len(text) <= 800 + 120
    assert "Digest shortened" in text
