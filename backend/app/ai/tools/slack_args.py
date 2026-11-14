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
