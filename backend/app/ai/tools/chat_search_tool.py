from datetime import datetime, timedelta
from typing import Any

from app.ai.tools.base import BaseTool
from app.ai.tools.context import ToolContext
from app.repositories.message_repository import search_messages

# Messages are stored in UTC; users are in India (IST).
LOCAL_UTC_OFFSET = timedelta(hours=5, minutes=30)

MAX_RESULTS = 6
SNIPPET_CHARS = 250
MAX_KEYWORDS = 5


def _parse_day(value: str, current_year: int) -> datetime:
    """Parse YYYY-MM-DD, or MM-DD (current year assumed)."""

    value = value.strip()

    try:
        return datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        return datetime.strptime(f"{current_year}-{value}", "%Y-%m-%d")


def _normalize_keywords(raw: Any) -> list[str]:
    if raw is None:
        return []

    if isinstance(raw, str):
        raw = [raw]

    if not isinstance(raw, (list, tuple)):
        return []

    cleaned = [str(k).strip() for k in raw if str(k).strip()]

    return cleaned[:MAX_KEYWORDS]


def _snippet(text: str, keywords: list[str], size: int = SNIPPET_CHARS) -> str:
    text = " ".join((text or "").split())

    if len(text) <= size:
        return text

    lower = text.lower()
    hits = [
        lower.find(k.lower())
        for k in keywords
        if lower.find(k.lower()) >= 0
    ]
    pos = min(hits) if hits else 0

    start = max(0, pos - size // 4)
    piece = text[start:start + size]

    if start > 0:
        piece = "…" + piece

    if start + size < len(text):
        piece = piece + "…"

    return piece


class ChatSearchTool(BaseTool):
    """
    Search earlier Vibe chats of the current workspace.

    Scope is controlled by the application (ToolContext), never by
    the model: only this workspace, never the current chat.
    """

    def __init__(self, context: ToolContext):
        self.context = context

    @property
    def name(self) -> str:
        return "search_chats"

    @property
    def description(self) -> str:
        return (
            "Search the user's earlier Vibe chats (saved messages) in "
            "this workspace by keywords and/or date. Use it when the "
            "user asks what was discussed, decided or changed in a "
            "previous chat or on a past date. Dates are YYYY-MM-DD "
            "(or MM-DD if the year is unknown). For relative periods "
            "like 'last week' use last_days. Results are short "
            "snippets and may be partial."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "keywords": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Up to 5 short keywords (any match).",
                },
                "date_from": {
                    "type": "string",
                    "description": "Start day, YYYY-MM-DD or MM-DD.",
                },
                "date_to": {
                    "type": "string",
                    "description": (
                        "End day (inclusive). Defaults to date_from."
                    ),
                },
                "last_days": {
                    "type": "integer",
                    "description": "Search only the last N days (1-90).",
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
                last = (
                    _parse_day(str(date_to), year) if date_to else first
                )
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

        if not kws and start is None and end is None:
            return {
                "success": False,
                "error": "Give keywords, a date, or last_days.",
            }

        rows = search_messages(
            db=self.context.db,
            workspace_id=self.context.workspace_id,
            exclude_chat_id=self.context.chat_id,
            keywords=kws,
            start=start,
            end=end,
            limit=MAX_RESULTS,
        )

        results = []

        # Repository returns newest first; show oldest first.
        for message, chat in reversed(list(rows)):
            local_time = message.created_at + LOCAL_UTC_OFFSET

            results.append(
                {
                    "chat_id": chat.id,
                    "chat_title": chat.title,
                    "role": message.role,
                    "time": local_time.strftime("%Y-%m-%d %H:%M") + " IST",
                    "snippet": _snippet(message.content, kws),
                }
            )

        return {
            "success": True,
            "count": len(results),
            "may_have_more": len(results) >= MAX_RESULTS,
            "messages": results,
        }
