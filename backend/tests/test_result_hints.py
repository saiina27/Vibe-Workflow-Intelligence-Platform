import json

from app.ai.tool_calling import ToolCallingService

bound = ToolCallingService._bound_tool_result


def mcp(payload):
    return {
        "success": True,
        "data": {"content": [{"type": "text", "text": json.dumps(payload)}]},
    }


def commit(i):
    return {
        "sha": f"{i:040x}",
        "commit": {
            "message": f"Commit {i}",
            "author": {"name": "Saina", "date": "2026-11-03T10:00:00Z"},
        },
        "author": {"login": "saiina27"},
    }


def test_a_list_result_says_how_many_rows_it_has(capsys):
    out = bound(mcp([commit(i) for i in range(1, 6)]))

    assert out["_count"] == 5
    assert "_columns" not in out
    assert "tool result for the model: 5 rows" in capsys.readouterr().out


def test_changed_file_rows_carry_the_column_hint():
    files = [
        {"filename": "a.py", "status": "modified", "additions": 3, "deletions": 1},
        {"filename": "b.py", "status": "added", "additions": 9, "deletions": 0},
    ]
    out = bound(mcp(files))

    assert out["_count"] == 2
    assert "File, Status, Additions, Deletions" in out["_columns"]


def test_a_truncated_list_counts_the_rows_it_kept(capsys):
    out = bound(mcp([dict(commit(i), pad="x" * 400) for i in range(1, 200)]))
    kept = len(json.loads(out["data"]))

    assert out["_truncated"] is True
    assert out["_count"] == kept
    assert f"{kept} of 199 rows" in capsys.readouterr().out


def test_objects_and_other_results_get_no_hints():
    out = bound(mcp({"name": "repo"}))

    assert "_count" not in out and "_columns" not in out
