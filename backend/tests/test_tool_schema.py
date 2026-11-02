from types import SimpleNamespace

import pytest

from app.ai.prompt_builder import build_prompt
from app.ai.tools.registry import ToolRegistry
from app.ai.tools.tool_schema import (
    MAX_DESCRIPTION,
    MAX_PARAM_DESCRIPTION,
    compact_definition,
    compact_schema,
    shorten,
)
from app.schemas.ai import ToolDefinition

LONG = (
    "Get list of commits of a branch in a GitHub repository. Returns at "
    "least 30 results per page by default, but can return more if specified "
    "using the perPage parameter (up to 100). Pagination is supported "
    "through the page parameter and results are sorted newest first."
)


def schema():
    return {
        "type": "object",
        "title": "ListCommitsInput",
        "properties": {
            "owner": {"type": "string", "description": "Repository owner " + "x" * 300},
            "title": {"type": "string", "description": "A parameter that is named title"},
            "description": {"type": "string"},
            "state": {"type": "string", "enum": ["open", "closed"], "default": "open",
                      "description": "State filter"},
            "labels": {
                "type": "array",
                "items": {"type": "string", "description": "Label " + "y" * 300},
                "examples": [["bug"]],
            },
        },
        "required": ["owner"],
        "additionalProperties": False,
    }


# ---------------- text ----------------

def test_short_text_is_unchanged_and_whitespace_is_normalised():
    assert shorten("A short one.", 160) == "A short one."
    assert shorten("two   lines\nhere", 160) == "two lines here"
    assert shorten(None, 10) == ""


def test_long_text_is_cut_at_a_sentence_end():
    out = shorten(LONG, MAX_DESCRIPTION)

    assert out == "Get list of commits of a branch in a GitHub repository."
    assert len(out) <= MAX_DESCRIPTION


def test_text_without_sentence_ends_is_cut_at_a_word():
    out = shorten("word " * 100, 60)

    assert len(out) <= 63 and out.endswith("...")
    assert " wor..." not in out


# ---------------- schema ----------------

def test_schema_keeps_structure_and_shortens_descriptions():
    out = compact_schema(schema())

    assert set(out["properties"]) == {"owner", "title", "description", "state", "labels"}
    assert out["required"] == ["owner"]
    assert out["additionalProperties"] is False
    assert out["properties"]["state"] == {
        "type": "string", "enum": ["open", "closed"], "default": "open",
        "description": "State filter",
    }
    assert out["properties"]["owner"]["type"] == "string"
    assert len(out["properties"]["owner"]["description"]) <= MAX_PARAM_DESCRIPTION + 3
    assert len(out["properties"]["labels"]["items"]["description"]) <= MAX_PARAM_DESCRIPTION + 3


def test_noise_keys_go_but_properties_named_like_them_stay():
    out = compact_schema(schema())

    assert "title" not in out
    assert "examples" not in out["properties"]["labels"]
    assert out["properties"]["title"]["description"] == "A parameter that is named title"
    assert "description" in out["properties"]


def test_the_original_schema_is_not_modified():
    original = schema()
    compact_schema(original)

    assert original["title"] == "ListCommitsInput"
    assert len(original["properties"]["owner"]["description"]) > 200


def test_compaction_cuts_a_realistic_definition_by_more_than_half():
    big = {
        "type": "object",
        "properties": {
            f"p{i}": {"type": "string", "description": "d" * 300} for i in range(10)
        },
    }
    definition = ToolDefinition(name="list_commits", description=LONG * 3, parameters=big)

    small = compact_definition(definition)

    assert len(str(small.model_dump())) < len(str(definition.model_dump())) / 2
    assert small.name == "list_commits"
    assert set(small.parameters["properties"]) == set(big["properties"])


# ---------------- registry: only MCP tools are compacted ----------------

class FakeTool:
    def __init__(self, name, plugin=None):
        self.name = name
        self.description = LONG
        self.parameters = schema()
        self.plugin_name = plugin


def prompt_for(text):
    return build_prompt(
        memories=[], conversation_summary=None,
        history=[SimpleNamespace(role="user", content=text)],
        knowledge_chunks=[], include_memories=False, include_knowledge=False,
    )


def definitions(text):
    registry = ToolRegistry()

    for name in ("get_me", "list_commits", "create_pull_request"):
        registry.register(FakeTool(name, "github"))

    for name in ("search_web", "search_knowledge", "search_memory"):
        registry.register(FakeTool(name))

    return {d.name: d for d in registry.definitions_for_prompt(prompt_for(text))}


def test_mcp_tools_are_compacted_and_our_own_tools_are_not():
    defs = definitions("show the latest commits of my repo X")

    assert {"list_commits", "get_me", "search_memory"} <= set(defs)
    assert "create_pull_request" not in defs

    assert len(defs["list_commits"].description) <= MAX_DESCRIPTION
    assert "title" not in defs["list_commits"].parameters

    assert defs["search_memory"].description == LONG
    assert defs["search_memory"].parameters["title"] == "ListCommitsInput"


def test_the_same_tools_are_exposed_as_before():
    names = set(definitions("show the latest commits of my repo X"))

    assert names == {"list_commits", "get_me", "search_web", "search_knowledge", "search_memory"}
