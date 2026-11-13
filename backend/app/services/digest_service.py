import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.chat import Chat
from app.models.dev_event import DevEvent
from app.models.message import Message
from app.models.tracked_repo import TrackedRepo
from app.models.workspace_memory import MemoryType, WorkspaceMemory

IST = timedelta(hours=5, minutes=30)

MAX_DAYS = 90
MAX_COMMITS_PER_DAY = 8
MAX_PRS_PER_DAY = 6
MAX_DECISIONS_PER_DAY = 5
MAX_CHATS_PER_DAY = 6
MAX_SLACK_PER_DAY = 6
MAX_ROWS = 1000
MAX_MARKDOWN_CHARS = 14000

MONTHS = [
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
]


# ------------------------------------------------------------
# Period (days are Indian Standard Time days)
# ------------------------------------------------------------

def clamp_days(days) -> int:
    try:
        days = int(days)
    except (TypeError, ValueError):
        days = 7

    return max(1, min(days, MAX_DAYS))


def period_bounds(days, now_utc: datetime | None = None):
    """(start in UTC, first IST day, last IST day). 1 day means today."""

    days = clamp_days(days)
    now_utc = now_utc or datetime.utcnow()

    last = (now_utc + IST).date()
    first = last - timedelta(days=days - 1)
    start_utc = datetime(first.year, first.month, first.day) - IST

    return start_utc, first, last


def ist_day(value: datetime):
    return (value + IST).date()


# ------------------------------------------------------------
# Reading the database (no LLM, nothing is written)
# ------------------------------------------------------------

def fetch_events(db: Session, workspace_id: int, start_utc: datetime) -> list[dict]:
    rows = (
        db.query(DevEvent)
        .filter(
            DevEvent.workspace_id == workspace_id,
            DevEvent.occurred_at >= start_utc,
        )
        .order_by(DevEvent.occurred_at.desc())
        .limit(MAX_ROWS)
        .all()
    )

    return [
        {
            "type": r.event_type,
            "repo": r.repo,
            "title": r.title,
            "author": r.author,
            "detail": r.detail,
            "external_id": r.external_id,
            "at": r.occurred_at,
        }
        for r in rows
    ]


def fetch_decisions(db: Session, workspace_id: int, start_utc: datetime) -> list[dict]:
    rows = (
        db.query(WorkspaceMemory)
        .filter(
            WorkspaceMemory.workspace_id == workspace_id,
            WorkspaceMemory.memory_type == MemoryType.DECISION,
            WorkspaceMemory.created_at >= start_utc,
            or_(
                WorkspaceMemory.expires_at.is_(None),
                WorkspaceMemory.expires_at > datetime.utcnow(),
            ),
        )
        .order_by(WorkspaceMemory.created_at.desc())
        .limit(200)
        .all()
    )

    return [
        {"title": r.title, "content": r.content, "at": r.created_at}
        for r in rows
    ]


def fetch_chat_activity(db: Session, workspace_id: int, start_utc: datetime) -> dict:
    """The user's questions in the period, and the titles of those chats."""

    rows = (
        db.query(Message.chat_id, Message.created_at)
        .join(Chat, Chat.id == Message.chat_id)
        .filter(
            Chat.workspace_id == workspace_id,
            Message.role == "user",
            Message.created_at >= start_utc,
        )
        .order_by(Message.created_at.desc())
        .limit(MAX_ROWS * 5)
        .all()
    )

    ids = sorted({r[0] for r in rows})
    chats = {}

    if ids:
        for chat in db.query(Chat).filter(Chat.id.in_(ids)).all():
            chats[chat.id] = (chat.title, chat.topic)

    return {"rows": [(r[0], r[1]) for r in rows], "chats": chats}


def synced_through(db: Session, workspace_id: int):
    values = [
        r[0]
        for r in db.query(TrackedRepo.last_synced_at)
        .filter(TrackedRepo.workspace_id == workspace_id)
        .all()
        if r[0]
    ]

    return max(values) if values else None


def _safe(db, label, notes, default, call):
    """A failing section never breaks the digest; it is named in a note."""

    try:
        return call()
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass

        notes.append(f"{label} could not be loaded.")

        return default


# ------------------------------------------------------------
# Grouping and writing
# ------------------------------------------------------------

def assemble(events, decisions, chat_data, synced, first, last, notes) -> dict:
    days = defaultdict(
        lambda: {
            "commits": [],
            "prs": [],
            "slack": [],
            "decisions": [],
            "chats": defaultdict(int),
        }
    )

    for e in events:
        day = ist_day(e["at"])

        if not (first <= day <= last):
            continue

        if e["type"] == "commit":
            days[day]["commits"].append(e)
        elif e["type"] == "pull_request":
            days[day]["prs"].append(e)
        elif e["type"] == "slack_message":
            days[day]["slack"].append(e)

    for d in decisions:
        day = ist_day(d["at"])

        if first <= day <= last:
            days[day]["decisions"].append(d)

    chat_ids = set()
    questions = 0

    for chat_id, at in chat_data.get("rows", []):
        day = ist_day(at)

        if first <= day <= last:
            days[day]["chats"][chat_id] += 1
            chat_ids.add(chat_id)
            questions += 1

    counts = {
        "commits": sum(len(b["commits"]) for b in days.values()),
        "pull_requests": sum(len(b["prs"]) for b in days.values()),
        "slack_messages": sum(len(b["slack"]) for b in days.values()),
        "decisions": sum(len(b["decisions"]) for b in days.values()),
        "chats": len(chat_ids),
        "questions": questions,
    }

    return {
        "days": dict(days),
        "chats": chat_data.get("chats", {}),
        "counts": counts,
        "related": find_related(days),
        "synced": synced,
        "first": first,
        "last": last,
        "notes": notes,
    }


# ------------------------------------------------------------
# "Probably related": a guess from shared rare words and nearby dates.
# It never says one thing caused another.
# ------------------------------------------------------------

MAX_RELATED = 8
MAX_RELATED_ITEMS = 400
GENERIC_SHARE = 0.3
LINK_WINDOW_DAYS = 1
DECISION_WINDOW_DAYS = 7

STOPWORDS = {
    "about", "added", "adding", "after", "again", "before", "being", "change",
    "changes", "chats", "check", "code", "commit", "commits", "could", "each",
    "first", "fixed", "from", "have", "include", "into", "latest", "message",
    "more", "most", "needs", "never", "only", "other", "project", "same",
    "should", "some", "tests", "their", "them", "then", "there", "these",
    "this", "those", "update", "updated", "using", "vibe", "well", "when",
    "which", "with", "work", "works", "would",
}


def _tokens(text) -> set:
    return {
        word
        for word in re.findall(r"[a-z0-9_]{5,}", (text or "").lower())
        if word not in STOPWORDS and not word.isdigit()
    }


def _related_items(days) -> list:
    items = []

    for day in sorted(days, reverse=True):
        bucket = days[day]

        for e in bucket["commits"]:
            sha = (e["external_id"] or "")[:7]
            title = _clip(e["title"], 60)
            items.append({"kind": "commit", "day": day, "text": e["title"],
                          "label": f'commit `{sha}` "{title}"'})

        for e in bucket["prs"]:
            title = _clip(e["title"], 60)
            items.append({"kind": "pull_request", "day": day, "text": e["title"],
                          "label": f'pull request "{title}"'})

        for e in bucket["slack"]:
            title = _clip(e["title"], 60)
            items.append({"kind": "slack", "day": day, "text": e["title"],
                          "label": f'Slack {e["repo"]} "{title}"'})

        for d in bucket["decisions"]:
            text = d["content"] or d["title"]
            title = _clip(text, 60)
            items.append({"kind": "decision", "day": day, "text": text,
                          "label": f'decision "{title}"'})

    return items[:MAX_RELATED_ITEMS]


def find_related(days) -> list:
    items = _related_items(days)
    count = len(items)

    if count < 2:
        return []

    token_sets = [_tokens(item["text"]) for item in items]
    frequency = Counter()

    for tokens in token_sets:
        frequency.update(tokens)

    # With a few items, "common" means nothing, so nothing is filtered.
    generic = (
        {t for t, n in frequency.items() if n / count > GENERIC_SHARE}
        if count >= 5
        else set()
    )

    pairs = []

    for a in range(count):
        for b in range(a + 1, count):
            x, y = items[a], items[b]

            if x["kind"] == y["kind"]:
                continue

            window = (
                DECISION_WINDOW_DAYS
                if "decision" in (x["kind"], y["kind"])
                else LINK_WINDOW_DAYS
            )

            if abs((x["day"] - y["day"]).days) > window:
                continue

            shared = (token_sets[a] & token_sets[b]) - generic

            if shared:
                pairs.append((len(shared), a, b, sorted(shared)))

    pairs.sort(key=lambda p: (-p[0], p[1], p[2]))

    out = []
    used = set()

    for _size, a, b, shared in pairs:
        if a in used or b in used:
            continue

        used.update((a, b))
        out.append({"a": items[a]["label"], "b": items[b]["label"], "shared": shared[:3]})

        if len(out) == MAX_RELATED:
            break

    return out


def _plural(n: int, word: str) -> str:
    return f"{n} {word if n == 1 else word + 's'}"


def _fmt_day(day) -> str:
    return f"{day.day:02d} {MONTHS[day.month - 1]} {day.year}"


def _fmt_time(value: datetime) -> str:
    local = value + IST

    return f"{_fmt_day(local)} {local.hour:02d}:{local.minute:02d}"


def _clip(text, limit: int) -> str:
    text = " ".join(str(text or "").split())

    return text if len(text) <= limit else text[: limit - 3].rstrip() + "..."


def _group_chats(chats, info) -> list:
    """Chats with the same title are shown as one line:
    (title, topic, number of chats, number of questions)."""

    groups: dict = {}

    for chat_id, questions in chats:
        title, topic = info.get(chat_id, ("Chat", None))
        title = " ".join(str(title or "Chat").split())
        group = groups.setdefault(
            title.lower(),
            {"title": title, "topics": {}, "chats": 0, "questions": 0},
        )

        group["chats"] += 1
        group["questions"] += questions

        if topic:
            group["topics"][topic] = group["topics"].get(topic, 0) + 1

    rows = []

    for group in groups.values():
        topic = (
            max(group["topics"], key=lambda t: (group["topics"][t], t))
            if group["topics"]
            else None
        )
        rows.append((group["title"], topic, group["chats"], group["questions"]))

    rows.sort(key=lambda r: (-r[3], r[0]))

    return rows


def render_markdown(data: dict) -> str:
    first, last, counts = data["first"], data["last"], data["counts"]

    span = _fmt_day(first) if first == last else f"{_fmt_day(first)} to {_fmt_day(last)}"

    out = [f"# Vibe digest: {span} (IST)", ""]

    parts = [
        _plural(counts["commits"], "commit"),
        _plural(counts["pull_requests"], "pull request"),
    ]

    if counts.get("slack_messages"):
        parts.append(_plural(counts["slack_messages"], "Slack message"))

    parts += [
        _plural(counts["decisions"], "decision") + " recorded",
        _plural(counts["chats"], "chat")
        + f" ({_plural(counts['questions'], 'question')})",
    ]

    out.append("**" + ", ".join(parts) + "**")

    if data["synced"]:
        out.append(
            f"GitHub history is as of the last sync ({_fmt_time(data['synced'])} IST). "
            "Newer commits appear after you press Sync now."
        )
    else:
        out.append(
            "GitHub history has not been synced yet, so commits and pull "
            "requests are not included."
        )

    for note in data["notes"]:
        out.append(f"_Note: {note}_")

    days = data["days"]
    repos = {e["repo"] for b in days.values() for e in b["commits"] + b["prs"]}
    several_repos = len(repos) > 1

    if not days:
        out += ["", "_No activity found in this period._"]

    for day in sorted(days, reverse=True):
        bucket = days[day]
        out += ["", f"## {_fmt_day(day)}"]

        commits = bucket["commits"]

        if commits:
            out += ["", f"**Commits ({len(commits)})**"]

            for e in commits[:MAX_COMMITS_PER_DAY]:
                sha = (e["external_id"] or "")[:7]
                who = f" ({e['author']})" if e["author"] else ""
                repo = f" [{e['repo'].split('/')[-1]}]" if several_repos else ""
                out.append(f"- `{sha}` {_clip(e['title'], 120)}{who}{repo}")

            if len(commits) > MAX_COMMITS_PER_DAY:
                out.append(f"- ...and {len(commits) - MAX_COMMITS_PER_DAY} more")

        prs = bucket["prs"]

        if prs:
            out += ["", f"**Pull requests ({len(prs)})**"]

            for e in prs[:MAX_PRS_PER_DAY]:
                state = f" ({e['detail']})" if e["detail"] else ""
                who = f" by {e['author']}" if e["author"] else ""
                out.append(f"- {_clip(e['title'], 120)}{state}{who}")

            if len(prs) > MAX_PRS_PER_DAY:
                out.append(f"- ...and {len(prs) - MAX_PRS_PER_DAY} more")

        slack = bucket["slack"]

        if slack:
            out += ["", f"**Slack messages ({len(slack)})**"]

            for e in slack[:MAX_SLACK_PER_DAY]:
                who = f" {e['author']}" if e["author"] else ""
                out.append(f"- {e['repo']}{who}: {_clip(e['title'], 120)}")

            if len(slack) > MAX_SLACK_PER_DAY:
                out.append(f"- ...and {len(slack) - MAX_SLACK_PER_DAY} more")

        decisions = bucket["decisions"]

        if decisions:
            out += ["", f"**Decisions recorded ({len(decisions)})**"]

            for d in decisions[:MAX_DECISIONS_PER_DAY]:
                out.append(f"- {_clip(d['content'] or d['title'], 300)}")

            if len(decisions) > MAX_DECISIONS_PER_DAY:
                out.append(f"- ...and {len(decisions) - MAX_DECISIONS_PER_DAY} more")

        chats = sorted(bucket["chats"].items(), key=lambda kv: (-kv[1], kv[0]))

        if chats:
            out += ["", f"**Chats ({len(chats)})**"]
            groups = _group_chats(chats, data["chats"])

            for title, topic, chat_count, questions in groups[:MAX_CHATS_PER_DAY]:
                topic_text = f" [{topic}]" if topic else ""
                size = f"{_plural(chat_count, 'chat')}, " if chat_count > 1 else ""
                out.append(
                    f"- {_clip(title, 80)}{topic_text}: {size}{_plural(questions, 'question')}"
                )

            if len(groups) > MAX_CHATS_PER_DAY:
                out.append(f"- ...and {len(groups) - MAX_CHATS_PER_DAY} more")

    related = data.get("related") or []

    if related:
        out += [
            "",
            "## Probably related",
            "_A guess from shared words and nearby dates. Not confirmed._",
        ]

        for r in related:
            out.append(f"- {r['a']} and {r['b']} (shared: {', '.join(r['shared'])})")

    text = "\n".join(out)

    if len(text) > MAX_MARKDOWN_CHARS:
        cut = text[:MAX_MARKDOWN_CHARS].rsplit("\n", 1)[0]
        text = cut + "\n\n_(Digest shortened. Choose a shorter period for the full list.)_"

    return text


def build_digest(
    db: Session,
    workspace_id: int,
    days,
    now_utc: datetime | None = None,
) -> dict:
    start_utc, first, last = period_bounds(days, now_utc)
    notes: list[str] = []

    events = _safe(db, "Commits and pull requests", notes, [],
                   lambda: fetch_events(db, workspace_id, start_utc))
    decisions = _safe(db, "Decisions", notes, [],
                      lambda: fetch_decisions(db, workspace_id, start_utc))
    chat_data = _safe(db, "Chats", notes, {"rows": [], "chats": {}},
                      lambda: fetch_chat_activity(db, workspace_id, start_utc))
    synced = _safe(db, "The sync time", notes, None,
                   lambda: synced_through(db, workspace_id))

    data = assemble(events, decisions, chat_data, synced, first, last, notes)

    return {
        "markdown": render_markdown(data),
        "counts": data["counts"],
        "days": clamp_days(days),
        "synced_through": synced.isoformat() if synced else None,
        "notes": notes,
    }
