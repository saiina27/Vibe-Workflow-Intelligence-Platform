import json

from pydantic import BaseModel

from app.ai.tool_calling import MAX_LOGGED_RESULT_CHARS, _json_safe


class Block(BaseModel):
    type: str = "text"
    text: str = "hello"


class FakeCallToolResult(BaseModel):
    content: list[Block] = [Block()]
    isError: bool = False


def test_pydantic_result_becomes_plain_json():
    out = _json_safe({"success": True, "data": FakeCallToolResult()})

    json.dumps(out)
    assert out["data"]["content"][0]["text"] == "hello"
    assert out["success"] is True


def test_plain_values_unchanged():
    value = {"success": True, "data": [1, "a", None]}
    assert _json_safe(value) == value


def test_unknown_objects_become_strings():
    class Odd:
        def __str__(self):
            return "odd"

    assert _json_safe({"data": Odd()}) == {"data": "odd"}


def test_huge_result_is_truncated():
    big = {"data": "x" * (MAX_LOGGED_RESULT_CHARS + 500)}
    out = _json_safe(big)

    assert out["_truncated"] is True
    assert len(out["preview"]) == MAX_LOGGED_RESULT_CHARS
