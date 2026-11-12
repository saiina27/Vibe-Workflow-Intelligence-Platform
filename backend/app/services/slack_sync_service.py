import asyncio
import json
import re
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.models.dev_event import DevEvent
from app.models.tracked_slack_term import TrackedSlackTerm
from app.models.workspace import Workspace
from app.services import dev_events_service as dev

IST = timedelta(hours=5, minutes=30)

# The only tool Slack sync may call. Search only: nothing is posted.
ALLOWED_SLACK_SYNC_TOOLS = {"slack_search_public"}

MAX_TERMS = 20
RESULTS_PER_TERM = 20
SNIPPET_CHARS = 160

_TERM = re.compile(r"^[\w#.\- ]{2,60}$")


# ------------------------------------------------------------
# Watch words
# ------------------------------------------------------------

def clean_term(term) -> str:
    term = " ".join(str(term or "").split())

    if not _TERM.match(term):
        raise ValueError(
            "A watch word needs 2 to 60 letters, digits, spaces or # . _ -"
        )

    return term


def list_terms(db: Session, workspace_id: int) -> list:
    return (
        db.query(TrackedSlackTerm)
        .filter(TrackedSlackTerm.workspace_id == workspace_id)
        .order_by(TrackedSlackTerm.term)
        .all()
    )


def add_term(db: Session, workspace_id: int, term) -> TrackedSlackTerm:
    term = clean_term(term)
    existing = list_terms(db, workspace_id)

    if len(existing) >= MAX_TERMS:
        raise ValueError(f"At most {MAX_TERMS} watch words.")

    if any(t.term.lower() == term.lower() for t in existing):
        raise ValueError("That watch word is already added.")

    row = TrackedSlackTerm(workspace_id=workspace_id, term=term)
    db.add(row)
    db.commit()
    db.refresh(row)

    return row


def delete_term(db: Session, workspace_id: int, term_id: int) -> bool:
    row = (
        db.query(TrackedSlackTerm)
        .filter(
            TrackedSlackTerm.id == term_id,
            TrackedSlackTerm.workspace_id == workspace_id,
        )
        .first()
    )

    if row is None:
        return False

    db.delete(row)
    db.commit()

    return True


def delete_slack_events(db: Session, workspace_id: int) -> int:
    count = (
        db.query(DevEvent)
        .filter(DevEvent.workspace_id == workspace_id, DevEvent.source == "slack")
        .delete(synchronize_session=False)
    )
    db.commit()

    return count


# ------------------------------------------------------------
# Parsing the text that the Slack search tool returns
# ------------------------------------------------------------

_BLOCK = re.compile(r"(?m)^###\s*Result\s+\d+\s+of\s+\d+[ \t]*$")
_CHANNEL = re.compile(r"#?([^\s(]+)\s*(?:\(ID:\s*([A-Za-z0-9]+)\))?")
_LINK = re.compile(r"\((https?://[^)\s]+)\)")
_BODY = re.compile(
    r"(?ms)^Text:[ \t]*\n?(.*?)(?=^Context (?:before|after):|^---|\Z)"
)


def _field(block: str, name: str) -> str:
    match = re.search(rf"(?m)^{name}:[ \t]*(.*)$", block)

    return match.group(1).strip() if match else ""


def clean_snippet(text: str, limit: int = SNIPPET_CHARS) -> str:
    text = re.sub(r"<@[A-Z0-9]+\|([^>]+)>", r"@\1", text or "")
    text = re.sub(r"<@[A-Z0-9]+>", "@user", text)
    text = re.sub(r"<#[A-Z0-9]+\|([^>]+)>", r"#\1", text)
    text = re.sub(r"<https?:[^|>]+\|([^>]+)>", r"\1", text)
    text = re.sub(r"<(https?:[^>]+)>", r"\1", text)
    text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    text = " ".join(text.split())

    return text if len(text) <= limit else text[: limit - 3].rstrip() + "..."


def _when(ts, time_text):
    try:
        return datetime.utcfromtimestamp(float(ts))
    except (TypeError, ValueError, OverflowError, OSError):
        pass

    match = re.match(r"(\d{4}-\d{2}-\d{2}) (\d{2}:\d{2}:\d{2})", time_text or "")

    if match:
        local = datetime.strptime(
            f"{match.group(1)} {match.group(2)}", "%Y-%m-%d %H:%M:%S"
        )

        return local - IST

    return None


def parse_slack_results(text: str) -> list:
    """Events from one `slack_search_public` result (detailed format)."""

    raw = text or ""

    try:
        outer = json.loads(raw)

        if isinstance(outer, dict) and isinstance(outer.get("results"), str):
            raw = outer["results"]
    except ValueError:
        pass

    events = []

    for block in _BLOCK.split(raw)[1:]:
        channel_match = _CHANNEL.match(_field(block, "Channel"))

        if not channel_match:
            continue

        channel = channel_match.group(1)
        channel_id = channel_match.group(2) or ""
        ts = _field(block, "Message_ts")
        when = _when(ts, _field(block, "Time"))

        if when is None:
            continue

        body = _BODY.search(block)
        link = _LINK.search(_field(block, "Permalink").replace("\\/", "/"))
        author = re.sub(r"\s*\(ID:.*$", "", _field(block, "From")).strip()
        stamp = ts or str(int((when - datetime(1970, 1, 1)).total_seconds()))

        events.append(
            {
                "source": "slack",
                "repo": f"#{channel}"[:200],
                "event_type": "slack_message",
                "external_id": f"{channel_id or channel}:{stamp}"[:100],
                "title": clean_snippet(body.group(1) if body else "") or "(no text)",
                "author": author or None,
                "url": link.group(1)[:500] if link else None,
                "detail": None,
                "occurred_at": when,
            }
        )

    return events


# ------------------------------------------------------------
# Sync
# ------------------------------------------------------------

def sync_term(db: Session, workspace_id: int, term: str, call, tracked=None) -> dict:
    text = dev.result_text(
        call(
            "slack_search_public",
            {
                "keywords": [term],
                "limit": RESULTS_PER_TERM,
                "sort": "timestamp",
                "sort_dir": "desc",
                "response_format": "detailed",
            },
        )
    )

    events = parse_slack_results(text)
    counts = {"new": 0, "updated": 0, "same": 0}

    for event in events:
        counts[dev.upsert_event(db, workspace_id, event)] += 1

    if tracked is not None:
        tracked.last_synced_at = datetime.utcnow()

    db.commit()

    return {"term": term, "events": len(events), **counts}


def sync_terms(db: Session, workspace_id: int, call) -> list:
    """One failing word never stops the others."""

    results = []

    for row in list_terms(db, workspace_id):
        name = row.term

        try:
            results.append(sync_term(db, workspace_id, name, call, row))
        except Exception as exc:
            db.rollback()
            results.append({"term": name, "error": str(exc)[:200]})

    return results


def stale_terms(db: Session, user_id: int, now=None) -> list:
    from app.services.auto_sync_service import is_stale

    now = now or datetime.utcnow()
    out = []

    workspaces = (
        db.query(Workspace)
        .filter(Workspace.user_id == user_id)
        .order_by(Workspace.id)
        .all()
    )

    for workspace in workspaces:
        terms = [t for t in list_terms(db, workspace.id) if is_stale(t, now)]

        if terms:
            out.append((workspace.id, terms))

    return out


def _make_call(db, workspace_id: int, user_id: int, registry):
    from app.ai.tools.context import ToolContext
    from app.ai.tools.executor import ToolExecutor
    from app.mcp.runtime import mcp_permission_service

    mcp_permission_service.add_workspace_plugin(workspace_id, "slack")

    executor = ToolExecutor(
        registry,
        ToolContext(db=db, workspace_id=workspace_id, user_id=user_id),
        mcp_permission_service=mcp_permission_service,
    )

    def call(tool_name: str, arguments: dict):
        if tool_name not in ALLOWED_SLACK_SYNC_TOOLS:
            raise PermissionError(f"Tool '{tool_name}' is not allowed for sync.")

        return executor.execute(tool_name=tool_name, arguments=arguments)

    return call


def _connect(db, user_id: int, registry) -> None:
    from app.mcp.runtime import mcp_integration_manager

    asyncio.run(
        mcp_integration_manager.connect_slack(
            db=db, user_id=user_id, registry=registry
        )
    )


def run_slack_auto_sync(db, user_id: int, now=None, make_call=None, connect=None) -> list:
    """Refresh watch words whose saved messages are too old. Quiet when
    there is nothing to do; never raises for one failing word."""

    targets = stale_terms(db, user_id, now)

    if not targets:
        print("💬 Slack auto-sync: saved messages are fresh")
        return []

    from app.services.external_integration_service import get_user_integration

    if get_user_integration(db=db, user_id=user_id, provider="slack") is None:
        print("💬 Slack auto-sync skipped: Slack is not connected")
        return []

    from app.ai.tools.registry import ToolRegistry

    registry = ToolRegistry()
    (connect or _connect)(db, user_id, registry)
    make_call = make_call or _make_call
    results = []

    for workspace_id, terms in targets:
        call = make_call(db, workspace_id, user_id, registry)

        for row in terms:
            name = row.term

            try:
                result = sync_term(db, workspace_id, name, call, row)
                results.append(result)
                print(
                    f"💬 Slack auto-sync '{name}': {result['events']} messages "
                    f"({result['new']} new)"
                )
            except Exception as exc:
                db.rollback()
                results.append({"term": name, "error": str(exc)[:200]})
                print(f"💬 Slack auto-sync failed for '{name}': {str(exc)[:120]}")

    return results
