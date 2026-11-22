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

SLACK_MESSAGE_TOOLS = {"slack_search_public", "slack_search_public_and_private"}


def prefer_detailed(tool_name: str, arguments: Any) -> Any:
    if tool_name not in SLACK_MESSAGE_TOOLS or not isinstance(arguments, dict):
        return arguments

    if arguments.get("response_format") == "detailed":
        return arguments

    out = dict(arguments)
    out["response_format"] = "detailed"

    return out


def _text_items(node: Any, found: list, depth: int = 0) -> None:
    if depth > 4 or not isinstance(node, dict):
        return

    content = node.get("content")

    if isinstance(content, list):
        for item in content:
            if isinstance(item, dict) and isinstance(item.get("text"), str):
                found.append(item)

    _text_items(node.get("data"), found, depth + 1)


def compact_slack_result(tool_name: str, result: Any) -> Any:
    """Messages with channel, author, time and link, without the context
    lines. Anything unexpected is returned untouched."""

    if tool_name not in SLACK_MESSAGE_TOOLS:
        return result

    try:
        import copy
        import json

        from app.services.slack_sync_service import parse_slack_messages

        clone = copy.deepcopy(result)
        found: list = []
        _text_items(clone, found)

        if not found:
            return result

        messages = parse_slack_messages(found[0]["text"])

        if not messages:
            return result

        found[0]["text"] = json.dumps(
            {
                "count": len(messages),
                "messages": messages,
                "note": "Show the link of every message you mention.",
            },
            ensure_ascii=False,
        )

        print(f"💬 Slack result: {len(messages)} messages with links")

        return clone

    except Exception:
        return result
