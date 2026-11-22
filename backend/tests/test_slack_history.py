import importlib
import json
import pkgutil
from datetime import datetime
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.models

for _m in pkgutil.iter_modules(app.models.__path__):
    importlib.import_module(f"app.models.{_m.name}")

from app.ai.prompt_builder import build_prompt
from app.ai.tools.context import ToolContext
from app.ai.tools.executor import ToolExecutor
from app.ai.tools.history_search_tool import HistorySearchTool
from app.ai.tools.registry import ToolRegistry
from app.ai.tools.slack_args import clean_slack_keywords
from app.db.base import Base
from app.mcp.tool_adapter import MCPToolAdapter
from app.models.dev_event import DevEvent
from app.models.tracked_repo import TrackedRepo


# ---------------- cleaning the keywords ----------------

def clean(keywords, **extra):
    return clean_slack_keywords("slack_search_public", {"keywords": keywords, **extra})


def test_words_of_the_question_are_removed():
    assert clean(["deployment", "team"], channel_types="public") == {
        "keywords": ["deployment"], "channel_types": "public",
    }


def test_a_whole_question_inside_one_keyword_is_reduced_to_the_topic():
    assert clean(["what did the team say about deployment?"])["keywords"] == ["deployment"]


def test_real_topic_words_stay_and_duplicates_go():
    assert clean(["we", "decided", "Groq", "groq"])["keywords"] == ["we", "decided", "Groq"]


def test_when_every_word_is_noise_the_original_is_kept():
    arguments = {"keywords": ["team", "said"]}

    assert clean_slack_keywords("slack_search_public", arguments) is arguments


def test_other_tools_and_other_arguments_are_untouched():
    github = {"keywords": ["team"]}
    assert clean_slack_keywords("list_commits", github) is github

    nothing = {"natural_language_query": "what did the team say"}
    assert clean_slack_keywords("slack_search_public", nothing) is nothing

    assert clean_slack_keywords("slack_search_public", None) is None


def test_a_single_string_keyword_is_accepted():
    assert clean_slack_keywords("slack_search_public", {"keywords": "deployment team"})["keywords"] == ["deployment"]


class FakeClient:
    def __init__(self):
        self.calls = []

    def call_tool(self, tool_name, arguments):
        self.calls.append((tool_name, arguments))
        return {"ok": True}


class AllowAll:
    def is_tool_allowed(self, plugin_name, tool_name, context):
        return True


def test_the_executor_sends_the_cleaned_keywords_to_slack():
    client = FakeClient()
    registry = ToolRegistry()
    registry.register(MCPToolAdapter(
        client=client,
        tool=SimpleNamespace(name="slack_search_public", description="d",
                             input_schema={"type": "object", "properties": {}}),
        plugin_name="slack",
    ))

    executor = ToolExecutor(
        registry, ToolContext(db=None, workspace_id=1, user_id=1),
        mcp_permission_service=AllowAll(),
    )

    executor.execute("slack_search_public", {"keywords": ["deployment", "team"]})

    # message searches are asked for in the detailed format (it has the links)
    assert client.calls == [
        ("slack_search_public", {"keywords": ["deployment"], "response_format": "detailed"})
    ]


# ---------------- search_history includes Slack ----------------

@pytest.fixture
def tool():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine, tables=[DevEvent.__table__, TrackedRepo.__table__])
    session = sessionmaker(bind=engine)()

    def add(source, repo, kind, ext, title, url=None):
        session.add(DevEvent(
            workspace_id=1, source=source, repo=repo, event_type=kind, external_id=ext,
            title=title, author="saiina27", url=url, occurred_at=datetime(2026, 10, 6, 8, 0),
        ))

    add("github", "o/vibe", "commit", "abc", "Smart routing for deployment questions")
    add("slack", "#dev-updates", "slack_message", "C1:1", "Deployment failed on Render, checking logs",
        "https://x.slack.com/archives/C1/p1")
    session.commit()

    yield HistorySearchTool(ToolContext(db=session, workspace_id=1, user_id=1))

    session.close()


def test_slack_messages_are_found_by_type(tool):
    for alias in ("slack", "slack_message", "messages"):
        out = tool.execute(event_type=alias)

        assert out["count"] == 1
        assert out["events"][0]["type"] == "slack_message"
        assert out["events"][0]["repo"] == "#dev-updates"
        assert out["events"][0]["url"].startswith("https://x.slack.com")


def test_keywords_find_both_commits_and_slack_messages(tool):
    out = tool.execute(keywords=["deployment"], date_from="2026-10-06")

    assert out["count"] == 2
    assert {e["type"] for e in out["events"]} == {"commit", "slack_message"}


def test_commit_questions_do_not_get_slack_messages(tool):
    out = tool.execute(event_type="commits")

    assert [e["type"] for e in out["events"]] == ["commit"]


def test_the_description_mentions_slack(tool):
    assert "Slack" in tool.description
    assert "slack_message" in tool.parameters["properties"]["event_type"]["description"]


# ---------------- the prompt ----------------

def test_the_slack_rule_says_what_an_empty_search_means():
    prompt = build_prompt(
        [], None,
        [SimpleNamespace(role="user", content="what did the team say about deployment on Slack")],
        [], False, False,
    )

    assert "no Slack message matched X" in prompt
    assert "try that once before answering" in prompt
    assert "search_history" in prompt


# ---------------- Slack results with links ----------------

RAW = (
    "# Search Results for: \n\n## Messages (1 results)\n### Result 1 of 1\n"
    "Channel: #dev-updates (ID: C0C7YC4CBT2)\n"
    "From: saiina27 (ID: U0BTS5XB1D0) \n"
    "Time: 2026-10-06 19:17:15 IST\n"
    "Message_ts: 1791294435.376399\n"
    "Permalink: [link](https://vibe-development.slack.com/archives/C0C7YC4CBT2/p1791294435376399)\n"
    "Text: \nDeployment failed on Render, checking logs\n"
    "Context before: \n- From: (ID: U00) \n Message_ts: 1791294396.034029\n"
    " <@U0BTS5XB1D0|saiina27> has joined the channel\n"
    "Context after: \n- From: saiina27 (ID: U0BTS5XB1D0) \n Message_ts: 1791294476.060729\n"
    " We decided to use Groq as the fallback provider\n\n---\n\n"
)
SLACK_TEXT = json.dumps({"results": RAW, "pagination_info": "End of results"})


def test_the_detailed_format_is_asked_for_only_on_message_searches():
    from app.ai.tools.slack_args import prefer_detailed

    assert prefer_detailed("slack_search_public", {"keywords": ["a"]})["response_format"] == "detailed"
    assert prefer_detailed("slack_search_public_and_private", {})["response_format"] == "detailed"

    channels = {"keywords": ["a"]}
    assert prefer_detailed("slack_search_channels", channels) is channels

    done = {"response_format": "detailed"}
    assert prefer_detailed("slack_search_public", done) is done
    assert prefer_detailed("list_commits", None) is None


def test_a_slack_result_becomes_rows_with_links_and_no_context():
    from app.ai.tools.slack_args import compact_slack_result

    original = {"success": True, "data": {"content": [{"type": "text", "text": SLACK_TEXT}], "is_error": False}}
    out = compact_slack_result("slack_search_public", original)
    rows = json.loads(out["data"]["content"][0]["text"])

    assert rows["count"] == 1
    assert rows["messages"][0] == {
        "channel": "#dev-updates", "from": "saiina27", "time": "2026-10-06 19:17:15 IST",
        "link": "https://vibe-development.slack.com/archives/C0C7YC4CBT2/p1791294435376399",
        "text": "Deployment failed on Render, checking logs",
    }
    assert "joined the channel" not in json.dumps(out)
    assert original["data"]["content"][0]["text"] == SLACK_TEXT


def test_unexpected_slack_results_are_left_alone():
    from app.ai.tools.slack_args import compact_slack_result

    concise = {"data": {"content": [{"type": "text", "text": '{"results":"1. #dev-updates - saiina27: hi"}'}]}}

    assert compact_slack_result("slack_search_public", concise) is concise
    assert compact_slack_result("slack_search_channels", concise) is concise
    assert compact_slack_result("slack_search_public", "plain text") == "plain text"
    assert compact_slack_result("slack_search_public", {"data": None}) == {"data": None}


def test_the_executor_asks_for_detail_and_returns_links():
    class Client:
        def __init__(self):
            self.calls = []

        def call_tool(self, tool_name, arguments):
            self.calls.append((tool_name, arguments))
            return {"content": [{"type": "text", "text": SLACK_TEXT}], "is_error": False}

    client = Client()
    registry = ToolRegistry()
    registry.register(MCPToolAdapter(
        client=client,
        tool=SimpleNamespace(name="slack_search_public", description="d",
                             input_schema={"type": "object", "properties": {}}),
        plugin_name="slack",
    ))

    executor = ToolExecutor(
        registry, ToolContext(db=None, workspace_id=1, user_id=1),
        mcp_permission_service=AllowAll(),
    )

    result = executor.execute("slack_search_public", {"keywords": ["deployment", "team"], "response_format": "concise"})

    assert client.calls == [("slack_search_public", {"keywords": ["deployment"], "response_format": "detailed"})]
    assert "vibe-development.slack.com/archives/C0C7YC4CBT2/p1791294435376399" in json.dumps(result, default=str)
    assert "joined the channel" not in json.dumps(result, default=str)


# ---------------- result objects, and widening an empty search ----------------

EMPTY = json.dumps({"results": "# Search Results for: \n\nNo results found.\n"})


def raw(text):
    return {"content": [{"type": "text", "text": text}], "is_error": False}


class FakeContent:
    def __init__(self, text):
        self.type = "text"
        self.text = text


class FakeCallToolResult:
    """Like the MCP client's result: an object, not a dict."""

    def __init__(self, text):
        self.content = [FakeContent(text)]
        self.isError = False


def test_an_object_shaped_mcp_result_is_read_too():
    from app.ai.tools.slack_args import compact_slack_result

    out = compact_slack_result(
        "slack_search_public", {"success": True, "data": FakeCallToolResult(SLACK_TEXT)}
    )
    rows = json.loads(out["data"]["content"][0]["text"])

    assert rows["messages"][0]["link"].startswith("https://vibe-development.slack.com/")


def test_when_no_message_has_all_the_words_each_word_is_tried_alone():
    from app.ai.tools.slack_args import broaden_slack_search

    calls = []

    def run(arguments):
        calls.append(arguments["keywords"])
        return raw(SLACK_TEXT if arguments["keywords"] == ["render"] else EMPTY)

    out = broaden_slack_search(
        "slack_search_public",
        {"keywords": ["render", "failure"], "response_format": "detailed"},
        raw(EMPTY),
        run,
    )
    rows = json.loads(out["data"]["content"][0]["text"])

    assert calls == [["render"], ["failure"]]
    assert rows["count"] == 1 and rows["messages"][0]["matched"] == ["render"]
    assert "No message contains all of: render, failure" in rows["note"]


def test_nothing_is_widened_when_it_is_not_needed():
    from app.ai.tools.slack_args import broaden_slack_search

    def forbidden(arguments):
        raise AssertionError("must not search again")

    found = raw(SLACK_TEXT)
    empty = raw(EMPTY)

    assert broaden_slack_search("slack_search_public", {"keywords": ["a", "b"]}, found, forbidden) is found
    assert broaden_slack_search("slack_search_public", {"keywords": ["a"]}, empty, forbidden) is empty
    assert broaden_slack_search("slack_search_channels", {"keywords": ["a", "b"]}, empty, forbidden) is empty


def test_failing_or_empty_word_searches_return_the_original_result():
    from app.ai.tools.slack_args import broaden_slack_search

    empty = raw(EMPTY)

    def boom(arguments):
        raise RuntimeError("Slack said no")

    assert broaden_slack_search("slack_search_public", {"keywords": ["a", "b"]}, empty, boom) is empty
    assert broaden_slack_search("slack_search_public", {"keywords": ["a", "b"]}, empty, lambda a: raw(EMPTY)) is empty


def test_the_executor_widens_an_empty_search_and_returns_links():
    class Client:
        def __init__(self):
            self.calls = []

        def call_tool(self, tool_name, arguments):
            self.calls.append(arguments["keywords"])
            text = SLACK_TEXT if arguments["keywords"] == ["render"] else EMPTY
            return {"content": [{"type": "text", "text": text}], "is_error": False}

    client = Client()
    registry = ToolRegistry()
    registry.register(MCPToolAdapter(
        client=client,
        tool=SimpleNamespace(name="slack_search_public", description="d",
                             input_schema={"type": "object", "properties": {}}),
        plugin_name="slack",
    ))

    executor = ToolExecutor(
        registry, ToolContext(db=None, workspace_id=1, user_id=1),
        mcp_permission_service=AllowAll(),
    )

    result = executor.execute("slack_search_public", {"keywords": ["render", "failure"]})

    assert client.calls == [["render", "failure"], ["render"], ["failure"]]
    assert "vibe-development.slack.com" in json.dumps(result, default=str)
