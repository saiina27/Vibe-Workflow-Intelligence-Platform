from datetime import datetime, timedelta
from typing import Any

from app.ai.tools.base import BaseTool
from app.ai.tools.chat_search_tool import (
    LOCAL_UTC_OFFSET,
    _normalize_keywords,
    _parse_day,
)
from app.ai.tools.context import ToolContext
from app.services import dev_events_service as svc
from app.services import digest_service

MAX_RESULTS = 15

TYPE_ALIASES = {
    "commit": "commit",
    "commits": "commit",
    "pull_request": "pull_request",
    "pull_requests": "pull_request",
    "pr": "pull_request",
    "prs": "pull_request",
    "slack": "slack_message",
    "slack_message": "slack_message",
    "slack_messages": "slack_message",
    "message": "slack_message",
    "messages": "slack_message",
}


def _chats_line(chats: list) -> str:
    """A ready-made sentence about the chats of the period."""

    parts = []

    for chat in chats:
        n = chat["questions"]
        word = "question" if n == 1 else "questions"
        parts.append(f"{chat['title']} ({n} {word})")

    return "Vibe chats in this period: " + "; ".join(parts) + "."


COMPACT_ABOVE = 6


def _compact_events(events: list) -> tuple[list, dict]:
    """Shorter rows for long lists so the whole list reaches the model (a long
    list used to be cut). Values that repeat move to the top level."""

    top: dict[str, Any] = {}
    repos = {e["repo"] for e in events if e["type"] != "slack_message"}
    authors = {e["author"] for e in events if e["author"]}

    if len(repos) == 1:
        top["repo"] = next(iter(repos))

    if len(authors) == 1 and all(e["author"] for e in events):
        top["author"] = next(iter(authors))

    top["time_zone"] = "IST"

    rows = []

    for e in events:
        row: dict[str, Any] = {
            "type": e["type"],
            "time": e["time"].replace(" IST", ""),
            "title": e["title"],
        }

        if e["type"] == "slack_message":
            row["channel"] = e["repo"]

            if e["url"]:
                row["url"] = e["url"]
        elif "repo" not in top:
            row["repo"] = e["repo"]

        if "author" not in top and e["author"]:
            row["author"] = e["author"]

        if e["status"]:
            row["status"] = e["status"]

        rows.append(row)

    return rows, top


class HistorySearchTool(BaseTool):
    """
    Search the saved developer history (commits and pull requests that
    were synced into dev_events). Read-only; scope comes from the
    application's ToolContext, never from the model.
    """

    def __init__(self, context: ToolContext):
        self.context = context

    @property
    def name(self) -> str:
        return "search_history"

    @property
    def description(self) -> str:
        return (
            "Search the saved development history of the user's tracked "
            "GitHub repositories (commits and pull requests) and the saved Slack "
            "messages of the watch words, by date, "
            "keywords, type or repository. Use it for questions like "
            "'what changed on 5 Oct' or 'what did we do last week'. "
            "Dates are YYYY-MM-DD (or MM-DD); for relative periods use "
            "last_days. Data is as of the last sync, so it may miss "
            "very recent changes. For a date or period without keywords or a "
            "type it also lists the Vibe chats of that period."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "keywords": {
                    "type": ["array", "null"],
                    "items": {"type": "string"},
                    "description": "Up to 5 words matched in title or author.",
                },
                "date_from": {
                    "type": ["string", "null"],
                    "description": "Start day, YYYY-MM-DD or MM-DD.",
                },
                "date_to": {
                    "type": ["string", "null"],
                    "description": "End day (inclusive). Defaults to date_from.",
                },
                "last_days": {
                    "type": ["integer", "null"],
                    "description": "Only the last N days (1-90).",
                },
                "event_type": {
                    "type": ["string", "null"],
                    "description": "commit, pull_request or slack_message.",
                },
                "repo": {
                    "type": ["string", "null"],
                    "description": "Repository name (or part of it).",
                },
            },
            "required": [],
        }

    def _chats_in_window(self, start, end) -> list:
        """Titles and question counts of the Vibe chats in the window, from
        the database. Never raises; the asking chat is left out."""

        try:
            data = digest_service.fetch_chat_activity(
                self.context.db, self.context.workspace_id, start
            )
        except Exception:
            try:
                self.context.db.rollback()
            except Exception:
                pass

            return []

        counts: dict = {}

        for chat_id, at in data.get("rows", []):
            if end is not None and at >= end:
                continue

            if chat_id == self.context.chat_id:
                continue

            counts[chat_id] = counts.get(chat_id, 0) + 1

        by_title: dict = {}

        for chat_id, questions in counts.items():
            title, _topic = data.get("chats", {}).get(chat_id, ("Chat", None))
            title = " ".join(str(title or "Chat").split())[:80]
            by_title[title] = by_title.get(title, 0) + questions

        ordered = sorted(by_title.items(), key=lambda kv: (-kv[1], kv[0]))[:5]

        return [{"title": t, "questions": n} for t, n in ordered]

    def execute(
        self,
        keywords: Any = None,
        date_from: Any = None,
        date_to: Any = None,
        last_days: Any = None,
        event_type: Any = None,
        repo: Any = None,
        **_ignored: Any,
    ) -> dict[str, Any]:

        kws = _normalize_keywords(keywords)

        now_utc = datetime.utcnow()
        year = (now_utc + LOCAL_UTC_OFFSET).year

        start = None
        end = None

        try:
            if date_from:
                first = _parse_day(str(date_from), year)
                last = _parse_day(str(date_to), year) if date_to else first
                start = first - LOCAL_UTC_OFFSET
                end = last + timedelta(days=1) - LOCAL_UTC_OFFSET

            elif date_to:
                last = _parse_day(str(date_to), year)
                end = last + timedelta(days=1) - LOCAL_UTC_OFFSET

            elif last_days:
                days = max(1, min(int(last_days), 90))
                start = now_utc - timedelta(days=days)

        except (ValueError, TypeError):
            return {
                "success": False,
                "error": "Dates must be YYYY-MM-DD (or MM-DD).",
            }

        kind = TYPE_ALIASES.get(str(event_type).strip().lower()) if event_type else None
        repo_filter = str(repo).strip() if repo else None

        rows = svc.search_events(
            db=self.context.db,
            workspace_id=self.context.workspace_id,
            keywords=kws,
            start=start,
            end=end,
            event_type=kind,
            repo=repo_filter,
            limit=MAX_RESULTS,
        )

        chats = []

        if start is not None and not kws and not kind and not repo_filter:
            chats = self._chats_in_window(start, end)

        tracked = svc.list_tracked_repos(
            self.context.db, self.context.workspace_id
        )
        synced = [t.last_synced_at for t in tracked if t.last_synced_at]

        events = []

        for row in rows:
            local_time = row.occurred_at + LOCAL_UTC_OFFSET

            events.append(
                {
                    "type": row.event_type,
                    "repo": row.repo,
                    "time": local_time.strftime("%Y-%m-%d %H:%M") + " IST",
                    "title": row.title,
                    "author": row.author,
                    "status": row.detail,
                    "url": row.url,
                }
            )

        top: dict[str, Any] = {}

        if len(events) > COMPACT_ABOVE:
            events, top = _compact_events(events)

        result: dict[str, Any] = {
            "success": True,
            "count": len(events),
            "may_have_more": len(events) >= MAX_RESULTS,
            "events": events,
            "tracked_repos": len(tracked),
            "synced_through": (
                (max(synced) + LOCAL_UTC_OFFSET).strftime("%Y-%m-%d %H:%M")
                + " IST"
                if synced
                else None
            ),
        }

        result.update(top)

        if chats:
            result["chats"] = chats
            result["events"] = events + [
                {
                    "type": "vibe_chat",
                    "repo": "Vibe chats",
                    "time": "this period",
                    "title": chat["title"],
                    "author": None,
                    "status": f"{chat['questions']} question"
                    + ("" if chat["questions"] == 1 else "s"),
                    "url": None,
                }
                for chat in chats
            ]

        if not tracked:
            result["note"] = (
                "No repository is tracked yet. Ask the user to add a "
                "repository and run a sync."
            )

        return result
