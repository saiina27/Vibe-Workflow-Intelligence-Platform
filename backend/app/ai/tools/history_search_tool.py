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

MAX_RESULTS = 15

TYPE_ALIASES = {
    "commit": "commit",
    "commits": "commit",
    "pull_request": "pull_request",
    "pull_requests": "pull_request",
    "pr": "pull_request",
    "prs": "pull_request",
}


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
            "GitHub repositories (commits and pull requests) by date, "
            "keywords, type or repository. Use it for questions like "
            "'what changed on 5 Oct' or 'what did we do last week'. "
            "Dates are YYYY-MM-DD (or MM-DD); for relative periods use "
            "last_days. Data is as of the last sync, so it may miss "
            "very recent changes."
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
                    "description": "commit or pull_request.",
                },
                "repo": {
                    "type": ["string", "null"],
                    "description": "Repository name (or part of it).",
                },
            },
            "required": [],
        }

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

        if not tracked:
            result["note"] = (
                "No repository is tracked yet. Ask the user to add a "
                "repository and run a sync."
            )

        return result
