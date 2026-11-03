import json
from types import SimpleNamespace

from app.ai.prompt_builder import HISTORY_ANSWER_CHARS, build_prompt
from app.ai.tool_calling import ToolCallingService

bound = ToolCallingService._bound_tool_result
LIMIT = ToolCallingService.MAX_TOOL_RESULT_CHARS


def mcp(payload):
    return {
        "success": True,
        "data": {"content": [{"type": "text", "text": json.dumps(payload)}]},
    }


def rows_of(payload):
    return json.loads(bound(mcp(payload))["data"])


def commit(i):
    sha = f"{i:040x}"

    return {
        "sha": sha,
        "html_url": f"https://github.com/o/r/commit/{sha}",
        "commit": {
            "message": f"Commit number {i}\n\nLong body " + "x" * 300,
            "author": {
                "name": "Saina Yadav",
                "email": "a@b.c",
                "date": "2026-11-03T10:00:00Z",
            },
        },
        "author": {"login": "saiina27", "id": 1, "avatar_url": "x"},
        "committer": {"login": "web-flow"},
    }


def issue(i):
    return {
        "number": i,
        "title": f"Issue {i}",
        "state": "open",
        "html_url": "https://github.com/o/r/issues/1",
        "user": {"login": "saiina27", "avatar_url": "x"},
        "labels": [{"name": "bug", "color": "red"}],
        "created_at": "2026-10-01T00:00:00Z",
        "body": "long " * 100,
        "comments": 2,
    }


# ---------------- short rows ----------------

def test_ten_commits_now_fit_as_short_rows():
    payload = [commit(i) for i in range(1, 11)]
    assert len(json.dumps(payload)) > LIMIT

    out = bound(mcp(payload))
    rows = json.loads(out["data"])

    assert "_truncated" not in out and len(rows) == 10
    assert set(rows[0]) == {"sha", "message", "author", "date"}
    assert rows[0] == {
        "sha": f"{1:040x}",
        "message": "Commit number 1",
        "author": "Saina Yadav",
        "date": "2026-11-03",
    }
    assert "a@b.c" not in out["data"] and "html_url" not in out["data"]


def test_a_long_commit_list_is_still_cut_at_whole_rows_and_flagged():
    out = bound(mcp([commit(i) for i in range(1, 101)]))
    rows = json.loads(out["data"])

    assert out["_truncated"] is True and "of 100 items" in out["_note"]
    assert 12 < len(rows) < 100
    assert all(set(r) == {"sha", "message", "author", "date"} for r in rows)


def test_issue_and_pull_request_rows_drop_bodies_and_urls():
    rows = rows_of([issue(1), issue(2)])

    assert rows[0] == {
        "number": 1, "title": "Issue 1", "state": "open",
        "author": "saiina27", "date": "2026-10-01", "labels": ["bug"],
    }

    merged = dict(issue(3), merged_at="2026-10-02T00:00:00Z", draft=False)
    assert rows_of([merged])[0]["merged"] is True


def test_graphql_style_issues_inside_an_object_are_shortened_too():
    graphql = {
        "number": 7, "title": "Slow sync", "state": "OPEN",
        "author": {"login": "saiina27"}, "createdAt": "2026-10-05T00:00:00Z",
        "labels": {"nodes": [{"name": "perf"}]}, "body": "x" * 500,
    }
    data = json.loads(bound(mcp({"issues": [graphql], "totalCount": 1}))["data"])

    assert data["totalCount"] == 1
    assert data["issues"][0] == {
        "number": 7, "title": "Slow sync", "state": "OPEN",
        "author": "saiina27", "date": "2026-10-05", "labels": ["perf"],
    }


def test_changed_files_keep_zero_counts_and_lose_the_patch():
    files = [
        {"filename": f"a{i}.py", "status": "modified", "additions": i,
         "deletions": 0, "patch": "x" * 500, "sha": "s"}
        for i in range(5)
    ]
    rows = rows_of(files)

    assert rows[0] == {"file": "a0.py", "status": "modified", "additions": 0, "deletions": 0}
    assert "patch" not in json.dumps(rows)


def test_other_shapes_are_left_alone():
    branches = [{"name": "main", "commit": {"sha": "abc", "url": "u"}, "protected": False}]
    assert rows_of(branches) == branches

    assert rows_of([{"merged": False, "number": 0}]) == [{"merged": False, "number": 0}]
    assert rows_of({"name": "repo"}) == {"name": "repo"}


# ---------------- history ----------------

def turn(role, content):
    return SimpleNamespace(role=role, content=content)


def conversation(turns):
    prompt = build_prompt(
        memories=[], conversation_summary=None, history=turns,
        knowledge_chunks=[], include_memories=False, include_knowledge=False,
    )

    return prompt.split("CURRENT CONVERSATION")[1]


def test_older_assistant_answers_are_shortened_and_recent_ones_are_not():
    long = "word " * 400
    text = conversation([
        turn("user", "first question"),
        turn("assistant", long),
        turn("user", "second question"),
        turn("assistant", long),
        turn("user", "latest question"),
    ])

    assert text.count("[shortened]") == 1
    assert text.count(long.strip()) == 1
    assert "first question" in text and "second question" in text
    assert text.rstrip().endswith("RESPONSE INSTRUCTION") or "latest question" in text


def test_short_answers_and_user_messages_are_never_shortened():
    text = conversation([
        turn("user", "u" * 2000),
        turn("assistant", "short answer"),
        turn("user", "next"),
        turn("assistant", "ok"),
        turn("user", "last"),
    ])

    assert "[shortened]" not in text and "u" * 2000 in text


def test_the_limit_is_what_the_constant_says():
    text = conversation([
        turn("assistant", "a" * (HISTORY_ANSWER_CHARS + 50)),
        turn("user", "q"), turn("assistant", "x"), turn("user", "q2"),
    ])

    assert "a" * HISTORY_ANSWER_CHARS + " ... [shortened]" in text
    assert "a" * (HISTORY_ANSWER_CHARS + 1) not in text


# ---------------- prompt rules ----------------

def test_prompt_has_the_count_and_pr_file_rules():
    prompt = build_prompt(
        [], None, [turn("user", "hi")], [], False, False
    )

    assert "State only the number of items you actually list" in prompt
    assert "File, Status,\n  Additions, Deletions" in prompt
