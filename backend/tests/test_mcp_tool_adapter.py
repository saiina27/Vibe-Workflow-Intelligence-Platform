
from unittest.mock import MagicMock

import pytest
from mcp.types import Tool

from app.mcp.tool_adapter import MCPToolAdapter


def make_mcp_tool(
    name="github_get_pull_request",
    description="Get a GitHub pull request.",
):
    return Tool(
        name=name,
        description=description,
        inputSchema={
            "type": "object",
            "properties": {
                "owner": {
                    "type": "string",
                },
                "repo": {
                    "type": "string",
                },
                "pull_number": {
                    "type": "integer",
                },
            },
            "required": [
                "owner",
                "repo",
                "pull_number",
            ],
        },
    )


def test_mcp_tool_metadata_is_adapted():
    client = MagicMock()

    tool = make_mcp_tool()

    adapter = MCPToolAdapter(
        client=client,
        tool=tool,
        plugin_name="github",
    )

    assert adapter.name == "github_get_pull_request"

    assert (
        adapter.description
        == "Get a GitHub pull request."
    )

    assert adapter.parameters == {
        "type": "object",
        "properties": {
            "owner": {
                "type": "string",
            },
            "repo": {
                "type": "string",
            },
            "pull_number": {
                "type": "integer",
            },
        },
        "required": [
            "owner",
            "repo",
            "pull_number",
        ],
    }


def test_mcp_tool_execution_forwards_arguments():
    client = MagicMock()

    client.call_tool = MagicMock(
        return_value={
            "success": True,
            "data": "PR #42",
        }
    )

    adapter = MCPToolAdapter(
        client=client,
        tool=make_mcp_tool(),
        plugin_name="github",
    )

    result = adapter.execute(
        owner="octocat",
        repo="hello-world",
        pull_number=42,
    )

    assert result == {
        "success": True,
        "data": "PR #42",
    }

    client.call_tool.assert_called_once_with(
        tool_name="github_get_pull_request",
        arguments={
            "owner": "octocat",
            "repo": "hello-world",
            "pull_number": 42,
        },
    )


def test_mcp_tool_execution_supports_empty_arguments():
    client = MagicMock()

    client.call_tool = MagicMock(
        return_value="result",
    )

    tool = Tool(
        name="github_list_repositories",
        description="List repositories.",
        inputSchema={
            "type": "object",
            "properties": {},
        },
    )

    adapter = MCPToolAdapter(
        client=client,
        tool=tool,
        plugin_name="github",
    )

    result = adapter.execute()

    assert result == "result"

    client.call_tool.assert_called_once_with(
        tool_name="github_list_repositories",
        arguments={},
    )


def test_mcp_tool_execution_propagates_client_errors():
    client = MagicMock()

    client.call_tool = MagicMock(
        side_effect=RuntimeError(
            "MCP server unavailable"
        )
    )

    adapter = MCPToolAdapter(
        client=client,
        tool=make_mcp_tool(),
        plugin_name="github",
    )

    with pytest.raises(
        RuntimeError,
        match="MCP server unavailable",
    ):
        adapter.execute(
            owner="octocat",
            repo="hello-world",
            pull_number=42,
        )


def test_mcp_tool_adapter_uses_mcp_tool_name():
    client = MagicMock()

    client.call_tool = MagicMock(
        return_value="ok",
    )

    tool = make_mcp_tool(
        name="slack_search_messages",
        description="Search Slack messages.",
    )

    adapter = MCPToolAdapter(
        client=client,
        tool=tool,
        plugin_name="github",
    )

    result = adapter.execute(
        query="deployment failed",
    )

    assert result == "ok"

    client.call_tool.assert_called_once_with(
        tool_name="slack_search_messages",
        arguments={
            "query": "deployment failed",
        },
    )


def test_mcp_tool_adapter_preserves_plugin_identity():
    client = MagicMock()

    adapter = MCPToolAdapter(
        client=client,
        tool=make_mcp_tool(),
        plugin_name="github",
    )

    assert adapter.plugin_name == "github"


def test_mcp_tool_adapter_rejects_empty_plugin_name():
    client = MagicMock()

    with pytest.raises(
        ValueError,
        match="MCP plugin name cannot be empty",
    ):
        MCPToolAdapter(
            client=client,
            tool=make_mcp_tool(),
            plugin_name="   ",
        )
