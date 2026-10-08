import json
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from sqlalchemy.orm import Session

from app.models.dev_event import DevEvent
from app.models.tracked_repo import TrackedRepo

# The only tools sync may call. Read-only, hardcoded.
ALLOWED_SYNC_TOOLS = {
    "get_me",
    "list_commits",
    "list_pull_requests",
    "search_repositories",
}

COMMITS_LIMIT = 50
PRS_LIMIT = 20

REPO_PATTERN = re.compile(
    r"^[A-Za-z0-9_-][A-Za-z0-9_.-]*/[A-Za-z0-9_-][A-Za-z0-9_.-]*$"
)


def is_valid_repo(name: str | None) -> bool:
    return bool(REPO_PATTERN.match(name or ""))


# ------------------------------------------------------------
# Parsing tool results
# ------------------------------------------------------------

def _plain(item: Any) -> Any:
    """Convert MCP result objects to plain dict/list/str (no truncation)."""

    if item is None or isinstance(item, (str, int, float, bool)):
        return item

    if isinstance(item, dict):
        return {str(k): _plain(v) for k, v in item.items()}

    if isinstance(item, (list, tuple)):
        return [_plain(v) for v in item]

    dump = getattr(item, "model_dump", None)

    if callable(dump):
        try:
            return _plain(dump(mode="json"))
        except Exception:
            pass

    if hasattr(item, "__dict__"):
        return _plain(vars(item))

    return str(item)


def _text_of(node: Any) -> str:
    if isinstance(node, str):
        return node

    if isinstance(node, dict):
        if node.get("is_error") or node.get("isError"):
            raise RuntimeError("GitHub tool returned an error.")

        content = node.get("content")

        if isinstance(content, list):
            return "\n".join(
                c["text"]
                for c in content
                if isinstance(c, dict) and isinstance(c.get("text"), str)
            )

        if "data" in node:
            return _text_of(node["data"])

    return ""


def result_text(result: Any) -> str:
    return _text_of(_plain(result))


def parse_json_list(text: str) -> list:
    try:
        data = json.loads(text)
    except (ValueError, TypeError):
        return []

    if isinstance(data, dict):
        for key in ("items", "commits", "pull_requests", "repositories"):
            if isinstance(data.get(key), list):
                return data[key]
        return []

    return data if isinstance(data, list) else []


def _parse_time(value: Any) -> datetime | None:
    if not value or not isinstance(value, str):
        return None

    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None

    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)

    return parsed


def _first_line(text: Any) -> str:
    lines = str(text or "").strip().splitlines()
    return (lines[0] if lines else "").strip()[:500]


def parse_commits(repo: str, items: list) -> list[dict]:
    events = []

    for item in items:
        if not isinstance(item, dict):
            continue

        sha = item.get("sha")
        commit = item.get("commit") or {}
        commit_author = commit.get("author") or {}
        when = _parse_time(commit_author.get("date"))

        if not sha or when is None:
            continue

        author = (item.get("author") or {}).get("login") or commit_author.get(
            "name"
        )

        events.append(
            {
                "source": "github",
                "repo": repo,
                "event_type": "commit",
                "external_id": str(sha),
                "title": _first_line(commit.get("message")) or "(no message)",
                "author": author,
                "url": item.get("html_url"),
                "detail": None,
                "occurred_at": when,
            }
        )

    return events


def parse_pull_requests(repo: str, items: list) -> list[dict]:
    events = []

    for item in items:
        if not isinstance(item, dict):
            continue

        number = item.get("number")
        when = _parse_time(item.get("created_at"))

        if number is None or when is None:
            continue

        state = "merged" if item.get("merged") else item.get("state")

        events.append(
            {
                "source": "github",
                "repo": repo,
                "event_type": "pull_request",
                "external_id": str(number),
                "title": _first_line(item.get("title")) or "(no title)",
                "author": (item.get("user") or {}).get("login"),
                "url": item.get("html_url"),
                "detail": state,
                "occurred_at": when,
            }
        )

    return events


# ------------------------------------------------------------
# Storage
# ------------------------------------------------------------

def upsert_event(db: Session, workspace_id: int, data: dict) -> str:
    """Insert or update one event. Returns 'new', 'updated' or 'same'."""

    existing = (
        db.query(DevEvent)
        .filter(
            DevEvent.workspace_id == workspace_id,
            DevEvent.source == data["source"],
            DevEvent.repo == data["repo"],
            DevEvent.external_id == data["external_id"],
        )
        .first()
    )

    if existing is None:
        db.add(DevEvent(workspace_id=workspace_id, **data))
        return "new"

    changed = False

    for key in ("title", "author", "url", "detail", "occurred_at"):
        if getattr(existing, key) != data[key]:
            setattr(existing, key, data[key])
            changed = True

    return "updated" if changed else "same"


def sync_repo(
    db: Session,
    workspace_id: int,
    full_name: str,
    call: Callable[[str, dict], Any],
    tracked: TrackedRepo | None = None,
) -> dict:
    """
    Pull recent commits and PRs of one repo into dev_events.

    `call(tool_name, arguments)` runs a read-only GitHub tool.
    """

    if not is_valid_repo(full_name):
        raise ValueError("Repository must look like owner/repo.")

    owner, repo = full_name.split("/", 1)

    commits_text = result_text(
        call("list_commits", {"owner": owner, "repo": repo, "perPage": COMMITS_LIMIT})
    )
    prs_text = result_text(
        call(
            "list_pull_requests",
            {"owner": owner, "repo": repo, "state": "all", "perPage": PRS_LIMIT},
        )
    )

    events = parse_commits(full_name, parse_json_list(commits_text))
    events += parse_pull_requests(full_name, parse_json_list(prs_text))

    counts = {"new": 0, "updated": 0, "same": 0}

    for event in events:
        counts[upsert_event(db, workspace_id, event)] += 1

    if tracked is not None:
        tracked.last_synced_at = datetime.utcnow()

    db.commit()

    return {"repo": full_name, "events": len(events), **counts}


def list_events(
    db: Session,
    workspace_id: int,
    repo: str | None = None,
    event_type: str | None = None,
    days: int = 30,
    limit: int = 100,
) -> list[DevEvent]:
    since = datetime.utcnow() - timedelta(days=max(1, min(days, 365)))

    query = db.query(DevEvent).filter(
        DevEvent.workspace_id == workspace_id,
        DevEvent.occurred_at >= since,
    )

    if repo:
        query = query.filter(DevEvent.repo == repo)

    if event_type:
        query = query.filter(DevEvent.event_type == event_type)

    return (
        query.order_by(DevEvent.occurred_at.desc())
        .limit(max(1, min(limit, 200)))
        .all()
    )


# ------------------------------------------------------------
# Tracked repos
# ------------------------------------------------------------

def list_tracked_repos(db: Session, workspace_id: int) -> list[TrackedRepo]:
    return (
        db.query(TrackedRepo)
        .filter(TrackedRepo.workspace_id == workspace_id)
        .order_by(TrackedRepo.created_at)
        .all()
    )


def add_tracked_repo(db: Session, workspace_id: int, full_name: str) -> TrackedRepo:
    full_name = full_name.strip()

    if not is_valid_repo(full_name):
        raise ValueError("Repository must look like owner/repo.")

    existing = (
        db.query(TrackedRepo)
        .filter(
            TrackedRepo.workspace_id == workspace_id,
            TrackedRepo.full_name == full_name,
        )
        .first()
    )

    if existing is not None:
        return existing

    row = TrackedRepo(workspace_id=workspace_id, full_name=full_name)
    db.add(row)
    db.commit()
    db.refresh(row)

    return row


def delete_tracked_repo(db: Session, workspace_id: int, repo_id: int) -> bool:
    row = (
        db.query(TrackedRepo)
        .filter(
            TrackedRepo.id == repo_id,
            TrackedRepo.workspace_id == workspace_id,
        )
        .first()
    )

    if row is None:
        return False

    db.query(DevEvent).filter(
        DevEvent.workspace_id == workspace_id,
        DevEvent.repo == row.full_name,
    ).delete()

    db.delete(row)
    db.commit()

    return True


def parse_repo_names(text: str) -> list[str]:
    """Best-effort: full names from a search_repositories result."""

    names = []

    for item in parse_json_list(text):
        if not isinstance(item, dict):
            continue

        name = item.get("full_name")

        if not name:
            owner = item.get("owner")
            owner = owner.get("login") if isinstance(owner, dict) else owner
            if owner and item.get("name"):
                name = f"{owner}/{item['name']}"

        if name and is_valid_repo(name):
            names.append(name)

    return names
