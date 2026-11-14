import importlib
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

    assert client.calls == [("slack_search_public", {"keywords": ["deployment"]})]


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
