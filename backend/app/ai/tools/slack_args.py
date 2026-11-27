from typing import Any

# Slack search needs every keyword to be in a message. Words from the
# question itself ("team", "said") are in no message, so they are dropped.
NOISE = {
    "team", "teams", "said", "say", "says", "saying", "discuss", "discussed",
    "discussion", "discussions", "about", "slack", "message", "messages",
    "channel", "channels", "recent", "recently", "latest", "did", "what",
    "whats", "anyone", "any", "the", "on", "in", "for", "of", "and", "an",
    "to", "is", "was", "were", "from", "mention", "mentioned", "mentions",
    "post", "posted", "talk", "talked", "regarding", "there", "our", "my",
    "they", "please", "show", "find", "search", "tell", "me", "us", "does",
    "do", "has", "have", "had", "been", "anything", "something", "update",
    "updates", "thread", "threads",
}

_PUNCT = "?.,!:;\"'()"


def clean_slack_keywords(tool_name: str, arguments: Any) -> Any:
    """Keywords of a Slack search without the question's own words. Returns
    the same object when nothing changes, or when every word is noise."""

    if not str(tool_name).startswith("slack_search") or not isinstance(arguments, dict):
        return arguments

    raw = arguments.get("keywords")

    if isinstance(raw, str):
        raw = [raw]

    if not isinstance(raw, list) or not raw:
        return arguments

    cleaned = []
    seen = set()

    for item in raw:
        words = []

        for word in str(item).split():
            bare = word.strip(_PUNCT)

            if bare and bare.lower() not in NOISE:
                words.append(bare)

        text = " ".join(words)

        if text and text.lower() not in seen:
            seen.add(text.lower())
            cleaned.append(text)

    if not cleaned or cleaned == arguments.get("keywords"):
        return arguments

    print(f"🧹 Slack search words: {raw} -> {cleaned}")

    out = dict(arguments)
    out["keywords"] = cleaned

    return out


# ---------------------------------------------------------------------------
# Slack searches: ask for the detailed format (it has the link of every
# message) and hand the model compact rows instead of the raw text.
# ---------------------------------------------------------------------------

import contextvars

SLACK_MESSAGE_TOOLS = {"slack_search_public", "slack_search_public_and_private"}

# Sync saves the messages, so it needs the raw text of a search. Only answers
# in chat get the compact rows. A sync call sets this flag around the call.
_RAW = contextvars.ContextVar("slack_raw_result", default=False)


def raw_slack_call(fn):
    token = _RAW.set(True)

    try:
        return fn()
    finally:
        _RAW.reset(token)


def prefer_detailed(tool_name: str, arguments: Any) -> Any:
    if tool_name not in SLACK_MESSAGE_TOOLS or not isinstance(arguments, dict):
        return arguments

    if arguments.get("response_format") == "detailed":
        return arguments

    out = dict(arguments)
    out["response_format"] = "detailed"

    return out


def slack_messages_of(result: Any) -> list:
    """The messages of a Slack search result, whatever shape the MCP client
    returned (a dict, or an object with `content`). Same reader as the sync."""

    try:
        from app.services import dev_events_service as dev
        from app.services.slack_sync_service import parse_slack_messages

        return parse_slack_messages(dev.result_text(result))
    except Exception:
        return []


def _raw_text(result: Any) -> str:
    try:
        from app.services import dev_events_service as dev

        return dev.result_text(result) or ""
    except Exception:
        return ""


def build_slack_result(messages: list, note: str | None = None) -> dict:
    import json

    payload = {
        "count": len(messages),
        "messages": messages,
        "note": note or "Show the link of every message you mention.",
    }

    return {
        "success": True,
        "data": {
            "content": [
                {"type": "text", "text": json.dumps(payload, ensure_ascii=False)}
            ],
            "is_error": False,
        },
    }


def compact_slack_result(tool_name: str, result: Any) -> Any:
    """Messages with channel, author, time and link, without the context
    lines. Anything unexpected is returned untouched."""

    if tool_name not in SLACK_MESSAGE_TOOLS or _RAW.get():
        return result

    messages = slack_messages_of(result)

    if not messages:
        return result

    print(f"💬 Slack result: {len(messages)} messages with links")

    return build_slack_result(messages)


def broaden_slack_search(tool_name: str, arguments: Any, result: Any, run) -> Any:
    """Slack needs every keyword in one message. When nothing matched all of
    several words, try each word alone and return what matches any of them,
    saying which word matched. `run(arguments)` repeats the search."""

    if (
        tool_name not in SLACK_MESSAGE_TOOLS
        or not isinstance(arguments, dict)
        or _RAW.get()
    ):
        return result

    keywords = arguments.get("keywords")

    if not isinstance(keywords, list):
        return result

    words = [str(k).strip() for k in keywords if str(k).strip()][:3]

    if len(words) < 2 or "no results found" not in _raw_text(result).lower():
        return result

    merged: dict = {}

    for word in words:
        try:
            one = run({**arguments, "keywords": [word]})
        except Exception:
            continue

        for message in slack_messages_of(one):
            key = message["link"] or (message["channel"], message["time"], message["text"])
            entry = merged.setdefault(key, {"message": message, "words": []})
            entry["words"].append(word)

    if not merged:
        return result

    ordered = sorted(merged.values(), key=lambda e: -len(e["words"]))[:10]
    messages = [dict(e["message"], matched=e["words"]) for e in ordered]

    print(f"💬 Slack search widened: {len(messages)} messages match some of {words}")

    return build_slack_result(
        messages,
        "No message contains all of: "
        + ", ".join(words)
        + ". These messages contain at least one of the words (see matched). "
        "Say which word matched and show the link.",
    )
