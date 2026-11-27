import json
from types import SimpleNamespace

from app.ai.tools.context import ToolContext
from app.ai.tools.executor import ToolExecutor
from app.ai.tools.registry import ToolRegistry
from app.ai.tools.slack_args import compact_slack_result, raw_slack_call
from app.mcp.tool_adapter import MCPToolAdapter
from app.services import dev_events_service as dev
from app.services import slack_sync_service as ss

RAW = (
    "# Search Results for: \n\n## Messages (1 results)\n### Result 1 of 1\n"
    "Channel: #dev-updates (ID: C0C7YC4CBT2)\n"
    "From: saiina27 (ID: U0BTS5XB1D0) \n"
    "Time: 2026-10-06 19:17:15 IST\n"
    "Message_ts: 1791294435.376399\n"
    "Permalink: [link](https://vibe-development.slack.com/archives/C0C7YC4CBT2/p1791294435376399)\n"
    "Text: \nDeployment failed on Render, checking logs\n"
    "Context after: \n- From: x\n later\n\n---\n\n"
)
SLACK_TEXT = json.dumps({"results": RAW})


class Client:
    def call_tool(self, tool_name, arguments):
        return {"content": [{"type": "text", "text": SLACK_TEXT}], "is_error": False}


class AllowAll:
    def add_workspace_plugin(self, workspace_id, name):
        pass

    def is_tool_allowed(self, plugin_name, tool_name, context):
        return True


def registry():
    reg = ToolRegistry()
    reg.register(MCPToolAdapter(
        client=Client(),
        tool=SimpleNamespace(name="slack_search_public", description="d",
                             input_schema={"type": "object", "properties": {}}),
        plugin_name="slack",
    ))
    return reg


def test_the_sync_caller_gets_text_the_sync_parser_can_read(monkeypatch):
    monkeypatch.setattr("app.mcp.runtime.mcp_permission_service", AllowAll())

    call = ss._make_call(None, 5, 7, registry())
    events = ss.parse_slack_results(dev.result_text(call("slack_search_public", {"keywords": ["deployment"]})))

    assert len(events) == 1
    assert events[0]["external_id"] == "C0C7YC4CBT2:1791294435.376399"
    assert events[0]["title"] == "Deployment failed on Render, checking logs"


def test_chat_answers_still_get_the_compact_rows():
    executor = ToolExecutor(
        registry(), ToolContext(db=None, workspace_id=1, user_id=1),
        mcp_permission_service=AllowAll(),
    )
    text = json.dumps(executor.execute("slack_search_public", {"keywords": ["deployment"]}), default=str)

    assert "### Result" not in text
    assert "vibe-development.slack.com/archives/C0C7YC4CBT2/p1791294435376399" in text


def test_the_raw_flag_does_not_leak_after_a_sync_call():
    raw_slack_call(lambda: None)

    out = compact_slack_result("slack_search_public", {"content": [{"type": "text", "text": SLACK_TEXT}]})

    assert "messages" in json.dumps(out, default=str)
