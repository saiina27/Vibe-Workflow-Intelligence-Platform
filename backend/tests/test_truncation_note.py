from app.ai.tool_calling import ToolCallingService

bound = ToolCallingService._bound_tool_result
LIMIT = ToolCallingService.MAX_TOOL_RESULT_CHARS


def test_short_string_result_unchanged():
    out = bound({"success": True, "data": "small"})
    assert out["data"] == "small"
    assert "_truncated" not in out


def test_long_string_result_flagged():
    out = bound({"success": True, "data": "x" * (LIMIT + 50)})
    assert len(out["data"]) == LIMIT
    assert out["_truncated"] is True
    assert "shortened" in out["_note"]


def test_short_list_unchanged():
    out = bound({"success": True, "data": ["a", "b"]})
    assert out["data"] == ["a", "b"]
    assert "_truncated" not in out


def test_long_list_flagged():
    out = bound({"success": True, "data": ["y" * 2000, "z" * 2000]})
    assert out["_truncated"] is True


def test_long_dict_data_flagged():
    out = bound({"success": True, "data": {"k": "v" * (LIMIT + 10)}})
    assert out["_truncated"] is True


def test_non_dict_long_result_gets_note():
    out = bound("q" * (LIMIT + 10))
    assert "shortened" in out


def test_non_dict_short_result_unchanged():
    assert bound("hi") == "hi"


def test_error_still_bounded():
    out = bound({"success": False, "error": "e" * (LIMIT + 5)})
    assert len(out["error"]) == LIMIT
