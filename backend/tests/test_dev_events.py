import importlib
import json
import pkgutil
from datetime import datetime, timedelta

import pytest
from pydantic import BaseModel
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.models

for _m in pkgutil.iter_modules(app.models.__path__):
    importlib.import_module(f"app.models.{_m.name}")

from app.db.base import Base
from app.models.dev_event import DevEvent
from app.models.tracked_repo import TrackedRepo
from app.services import dev_events_service as svc


class Block(BaseModel):
    text: str
    type: str = "text"


class FakeResult(BaseModel):
    content: list[Block]
    is_error: bool = False


def wrap(payload) -> FakeResult:
    return FakeResult(content=[Block(text=json.dumps(payload))])


NOW = datetime.utcnow().replace(microsecond=0)


def iso(dt):
    return dt.isoformat() + "Z"


COMMITS = [
    {
        "sha": "e1d5d22dc9591666a017625bb5fba34206032fc8",
        "html_url": "https://github.com/o/r/commit/e1d5d22",
        "commit": {
            "message": "Tool logs: store results\n\nlong body here",
            "author": {
                "name": "Saina Yadav",
                "email": "private@example.com",
                "date": iso(NOW - timedelta(days=1)),
            },
        },
        "author": {"login": "saiina27"},
    },
    {
        "sha": "d4a1b52864b8902d519d52d51e3791f94c184886",
        "html_url": "https://github.com/o/r/commit/d4a1b52",
        "commit": {
            "message": "older commit",
            "author": {"name": "Saina Yadav", "date": iso(NOW - timedelta(days=60))},
        },
        "author": {"login": "saiina27"},
    },
]

PRS = [
    {
        "number": 1,
        "title": "Add test line",
        "state": "closed",
        "merged": False,
        "html_url": "https://github.com/o/r/pull/1",
        "user": {"login": "saiina27"},
        "created_at": iso(NOW - timedelta(days=2)),
    }
]


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(
        engine, tables=[TrackedRepo.__table__, DevEvent.__table__]
    )
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


def make_call(commits=COMMITS, prs=PRS, log=None):
    def call(name, args):
        if log is not None:
            log.append(name)
        return wrap(commits if name == "list_commits" else prs)

    return call


def test_result_text_reads_mcp_object_and_dict():
    assert json.loads(svc.result_text(wrap([1]))) == [1]
    assert json.loads(svc.result_text({"data": wrap([2])})) == [2]


def test_error_result_raises():
    bad = FakeResult(content=[Block(text="x")], is_error=True)
    with pytest.raises(RuntimeError):
        svc.result_text(bad)


def test_parse_commits_uses_first_line_login_and_no_email():
    events = svc.parse_commits("o/r", COMMITS)
    first = events[0]

    assert first["title"] == "Tool logs: store results"
    assert first["author"] == "saiina27"
    assert "private@example.com" not in json.dumps(first, default=str)


def test_parse_prs_marks_state():
    event = svc.parse_pull_requests("o/r", PRS)[0]
    assert event["event_type"] == "pull_request"
    assert event["external_id"] == "1"
    assert event["detail"] == "closed"

    merged = svc.parse_pull_requests("o/r", [{**PRS[0], "merged": True}])[0]
    assert merged["detail"] == "merged"


def test_sync_is_idempotent_and_updates_pr_state(db):
    first = svc.sync_repo(db, 1, "o/r", make_call())
    assert first["new"] == 3 and first["updated"] == 0

    again = svc.sync_repo(db, 1, "o/r", make_call())
    assert again["new"] == 0 and again["same"] == 3
    assert db.query(DevEvent).count() == 3

    changed = svc.sync_repo(
        db, 1, "o/r", make_call(prs=[{**PRS[0], "merged": True}])
    )
    assert changed["updated"] == 1
    pr = db.query(DevEvent).filter_by(event_type="pull_request").one()
    assert pr.detail == "merged"


def test_sync_only_calls_allowed_read_tools(db):
    log = []
    svc.sync_repo(db, 1, "o/r", make_call(log=log))

    assert set(log) == {"list_commits", "list_pull_requests"}
    assert set(log) <= svc.ALLOWED_SYNC_TOOLS
    assert not any(n.startswith(("create_", "push_", "merge_", "delete_")) for n in log)


@pytest.mark.parametrize("name", ["", "norepo", "a/b/c", "a b/c", "../x", None])
def test_invalid_repo_names_rejected(db, name):
    assert not svc.is_valid_repo(name)
    with pytest.raises(ValueError):
        svc.sync_repo(db, 1, name or "", make_call())


def test_list_events_filters_and_isolates_workspaces(db):
    svc.sync_repo(db, 1, "o/r", make_call())
    svc.sync_repo(db, 2, "o/r", make_call())

    recent = svc.list_events(db, 1, days=30)
    assert len(recent) == 2
    assert all(e.workspace_id == 1 for e in recent)

    assert len(svc.list_events(db, 1, days=90)) == 3
    assert [e.event_type for e in svc.list_events(db, 1, event_type="commit")] == ["commit"]


def test_tracked_repo_add_duplicate_and_delete_removes_events(db):
    a = svc.add_tracked_repo(db, 1, "o/r")
    b = svc.add_tracked_repo(db, 1, "o/r")
    assert a.id == b.id

    svc.sync_repo(db, 1, "o/r", make_call(), a)
    assert a.last_synced_at is not None

    assert svc.delete_tracked_repo(db, 2, a.id) is False
    assert svc.delete_tracked_repo(db, 1, a.id) is True
    assert db.query(DevEvent).count() == 0


def test_parse_repo_names_best_effort():
    text = json.dumps({"items": [{"full_name": "o/r"}, {"owner": {"login": "o"}, "name": "x"}, {"bad": 1}]})
    assert svc.parse_repo_names(text) == ["o/r", "o/x"]
    assert svc.parse_repo_names("not json") == []
