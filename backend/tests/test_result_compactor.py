import json
from types import SimpleNamespace

from pydantic import BaseModel

from app.ai.prompt_builder import build_prompt
from app.ai.tool_calling import ToolCallingService
from app.ai.tools.result_compactor import compact_tool_result

LIMIT = ToolCallingService.MAX_TOOL_RESULT_CHARS
bound = ToolCallingService._bound_tool_result


class Block(BaseModel):
    text: str
    type: str = "text"


class FakeMCPResult(BaseModel):
    content: list[Block]
    is_error: bool = False


def commit(i):
    person = {
        "login": "saiina27",
        "id": 121892088,
        "profile_url": "https://github.com/saiina27",
        "avatar_url": "https://avatars.githubusercontent.com/u/121892088?v=4",
    }
    stamp = {
        "name": "Saina Yadav",
        "email": "private@example.com",
        "date": "2026-10-08T11:32:49Z",
    }
    sha = f"{i:040x}"

    return {
        "sha": sha,
        "html_url": f"https://github.com/o/r/commit/{sha}",
        "commit": {
            "message": f"Commit number {i}",
            "author": dict(stamp),
            "committer": dict(stamp),
        },
        "author": dict(person),
        "committer": dict(person),
    }


def mcp(payload):
    return {
        "success": True,
        "data": FakeMCPResult(content=[Block(text=json.dumps(payload))]),
    }


def test_five_commits_fit_without_losing_any():
    payload = [commit(i) for i in range(1, 6)]
    assert len(json.dumps(payload)) > LIMIT  # the old behaviour cut this

    out = bound(mcp(payload))

    assert "_truncated" not in out
    for i in range(1, 6):
        assert f"{i:040x}" in out["data"]

    assert "avatar_url" not in out["data"]
    assert "private@example.com" not in out["data"]


def test_long_list_is_cut_at_whole_items_and_flagged():
    out = bound(mcp([commit(i) for i in range(1, 101)]))

    items = json.loads(out["data"])

    assert out["_truncated"] is True
    assert "of 100 items" in out["_note"]
    assert 1 <= len(items) < 100
    assert len(out["data"]) <= LIMIT
    assert all("sha" in item for item in items)


def test_non_mcp_results_are_untouched():
    result = {"success": True, "data": {"memories": [{"id": 1}], "count": 1}}
    assert compact_tool_result(result, LIMIT) is result

    plain = {"success": True, "data": "small"}
    assert compact_tool_result(plain, LIMIT) is plain


def test_non_json_text_passes_through_without_the_wrapper():
    text = "# Slack results\n- #dev-updates: Deployment failed on Render"
    result = {
        "success": True,
        "data": FakeMCPResult(content=[Block(text=text)]),
    }

    assert bound(result)["data"] == text


def test_dict_payload_is_cleaned_and_keeps_real_fields():
    out = bound(
        mcp({"name": "repo", "owner": {"login": "o", "avatar_url": "x"}, "empty": None})
    )
    data = json.loads(out["data"])

    assert data == {"name": "repo", "owner": {"login": "o"}}


def test_false_and_zero_values_are_kept():
    out = bound(mcp([{"merged": False, "number": 0}]))
    assert json.loads(out["data"]) == [{"merged": False, "number": 0}]


def prompt_for(text):
    return build_prompt(
        memories=[], conversation_summary=None,
        history=[SimpleNamespace(role="user", content=text)],
        knowledge_chunks=[], include_memories=False,
        include_knowledge=False,
    )


def test_prompt_forbids_invented_rows():
    assert "Never add table rows" in prompt_for("hi")


def test_prompt_explains_how_to_reach_the_users_code():
    prompt = prompt_for("explain how the router works")

    assert 'explain X in my repo' in prompt
    assert "more than\n  twice" in prompt
