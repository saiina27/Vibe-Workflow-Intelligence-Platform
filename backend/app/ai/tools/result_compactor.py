import json
from typing import Any

# Fields that cost tokens but never help an answer. Emails are dropped
# too, so they are not sent to the model.
NOISE_KEYS = {
    "avatar_url", "profile_url", "gravatar_id", "node_id", "git_url",
    "events_url", "followers_url", "following_url", "gists_url",
    "organizations_url", "received_events_url", "repos_url",
    "starred_url", "subscriptions_url", "site_admin", "user_view_type",
    "comments_url", "statuses_url", "tree", "parents", "verification",
    "email",
}


def _dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def to_plain(item: Any) -> Any:
    """Convert MCP result objects to plain dict/list/str (no cutting)."""

    if item is None or isinstance(item, (str, int, float, bool)):
        return item

    if isinstance(item, dict):
        return {str(k): to_plain(v) for k, v in item.items()}

    if isinstance(item, (list, tuple)):
        return [to_plain(v) for v in item]

    dump = getattr(item, "model_dump", None)

    if callable(dump):
        try:
            return to_plain(dump(mode="json"))
        except Exception:
            pass

    if hasattr(item, "__dict__"):
        return to_plain(vars(item))

    return str(item)


def _text_blocks(data: Any) -> str | None:
    """Text of an MCP result ({content: [{type: text, text: ...}]})."""

    plain = to_plain(data)

    if not isinstance(plain, dict):
        return None

    content = plain.get("content")

    if not isinstance(content, list) or not content:
        return None

    if not all(
        isinstance(c, dict)
        and c.get("type") == "text"
        and isinstance(c.get("text"), str)
        for c in content
    ):
        return None

    return "\n".join(c["text"] for c in content)


def _clean(node: Any) -> Any:
    if isinstance(node, dict):
        out = {}

        for key, value in node.items():
            if key in NOISE_KEYS:
                continue

            if key == "committer" and "author" in node:
                continue

            cleaned = _clean(value)

            if cleaned is None or cleaned == "" or cleaned == [] or cleaned == {}:
                continue

            out[key] = cleaned

        return out

    if isinstance(node, list):
        return [_clean(v) for v in node]

    return node


def _day(value):
    return value[:10] if isinstance(value, str) and len(value) >= 10 else value


def _login(value):
    if isinstance(value, dict):
        return value.get("login") or value.get("name")

    return value if isinstance(value, str) else None


def _label_names(labels):
    if isinstance(labels, dict):
        labels = labels.get("nodes") or labels.get("edges") or []

    names = []

    for label in labels if isinstance(labels, list) else []:
        name = label.get("name") if isinstance(label, dict) else label

        if isinstance(name, str):
            names.append(name)

    return names


def _row(item):
    """One short row per commit, issue, pull request or changed file.
    Anything else is returned unchanged."""

    if not isinstance(item, dict):
        return item

    try:
        commit = item.get("commit")

        if isinstance(item.get("sha"), str) and isinstance(commit, dict):
            who = commit.get("author") if isinstance(commit.get("author"), dict) else {}
            first_line = (commit.get("message") or "").strip().split("\n")[0]

            row = {
                "sha": item["sha"],
                "message": first_line[:200],
                "author": who.get("name") or _login(item.get("author")),
                "date": _day(who.get("date")),
            }

            return {k: v for k, v in row.items() if v}

        if isinstance(item.get("filename"), str) and "status" in item:
            row = {
                "file": item["filename"],
                "status": item.get("status"),
                "additions": item.get("additions"),
                "deletions": item.get("deletions"),
            }

            return {k: v for k, v in row.items() if v is not None}

        if "number" in item and isinstance(item.get("title"), str):
            row = {
                "number": item["number"],
                "title": item["title"][:150],
                "state": item.get("state"),
                "author": _login(item.get("user") or item.get("author")),
                "date": _day(item.get("created_at") or item.get("createdAt")),
                "labels": _label_names(item.get("labels")) or None,
            }

            if item.get("draft"):
                row["draft"] = True

            if item.get("merged_at") or item.get("merged"):
                row["merged"] = True

            return {k: v for k, v in row.items() if v}

    except Exception:
        return item

    return item


def _slim(node):
    if isinstance(node, list):
        return [_row(item) for item in node]

    if isinstance(node, dict):
        for key in ("issues", "items", "pull_requests"):
            if isinstance(node.get(key), list):
                out = dict(node)
                out[key] = [_row(item) for item in node[key]]

                return out

    return node


def compact_tool_result(result: Any, max_chars: int) -> Any:
    """
    Make an MCP tool result smaller before it goes to the model.

    Results that are not MCP text results are returned unchanged.
    Long lists are cut at whole items and flagged as partial.
    """

    if not isinstance(result, dict) or "data" not in result:
        return result

    text = _text_blocks(result["data"])

    if text is None:
        return result

    try:
        parsed = json.loads(text)
    except (ValueError, TypeError):
        return {**result, "data": text}

    cleaned = _slim(_clean(parsed))

    if not isinstance(cleaned, list):
        return {**result, "data": _dumps(cleaned)}

    full = _dumps(cleaned)

    if len(full) <= max_chars:
        return {**result, "data": full}

    budget = max_chars - 120
    kept: list = []
    used = 2

    for item in cleaned:
        piece = _dumps(item)

        if kept and used + len(piece) + 1 > budget:
            break

        kept.append(item)
        used += len(piece) + 1

    note = (
        f"Showing {len(kept)} of {len(cleaned)} items in this page of "
        "results; the rest were left out to fit the size limit. This is "
        "not the total number of items in the repository. Tell the user "
        "the list is partial."
    )

    return {
        **result,
        "data": _dumps(kept),
        "_truncated": True,
        "_note": note,
    }
