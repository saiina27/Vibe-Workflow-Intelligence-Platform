from unittest.mock import Mock

import pytest

from app.ai.tools.context import ToolContext
from app.ai.tools.executor import ToolExecutor
from app.ai.tools.registry import ToolRegistry
from app.mcp.permissions import MCPPermissionService
from app.mcp.registry import (
    MCPPlugin,
    MCPPluginRegistry,
)
from app.mcp.server_manager import MCPServerConfig
from app.mcp.tool_adapter import MCPToolAdapter


def make_context(
    workspace_id=1,
    user_id=1,
    allowed_tools=None,
):
    return ToolContext(
        db=None,
        workspace_id=workspace_id,
        user_id=user_id,
        allowed_tools=allowed_tools,
    )


def make_permission_service():
    plugin_registry = MCPPluginRegistry()

    plugin_registry.register(
        MCPPlugin(
            name="github",
            display_name="GitHub",
            server_config=MCPServerConfig(
                name="github",
                command="python",
            ),
            enabled=True,
        )
    )

    return MCPPermissionService(
        registry=plugin_registry,
    )


def make_mcp_tool(client):
    mcp_tool = Mock()

    mcp_tool.name = "github_get_pull_request"
    mcp_tool.description = "Get a GitHub pull request."
    mcp_tool.input_schema = {
        "type": "object",
        "properties": {
            "owner": {"type": "string"},
            "repo": {"type": "string"},
            "pull_number": {"type": "integer"},
        },
        "required": [
            "owner",
            "repo",
            "pull_number",
        ],
    }

    return MCPToolAdapter(
        client=client,
        tool=mcp_tool,
        plugin_name="github",
    )


def make_executor(
    context,
    client,
):
    registry = ToolRegistry()

    registry.register(
        make_mcp_tool(client)
    )

    permission_service = make_permission_service()

    return ToolExecutor(
        registry=registry,
        context=context,
        mcp_permission_service=permission_service,
    )


def test_denied_mcp_plugin_blocks_execution():
    client = Mock()

    context = make_context()

    executor = make_executor(
        context=context,
        client=client,
    )

    with pytest.raises(PermissionError):
        executor.execute(
            tool_name="github_get_pull_request",
            arguments={
                "owner": "test",
                "repo": "repo",
                "pull_number": 1,
            },
        )

    client.call_tool.assert_not_called()


def test_allowed_mcp_plugin_allows_execution():
    client = Mock()

    client.call_tool.return_value = {
        "number": 1,
        "title": "Test PR",
    }

    context = make_context()

    permission_service = make_permission_service()

    permission_service.set_workspace_plugins(
        workspace_id=1,
        plugins={"github"},
    )

    registry = ToolRegistry()

    registry.register(
        make_mcp_tool(client)
    )

    executor = ToolExecutor(
        registry=registry,
        context=context,
        mcp_permission_service=permission_service,
    )

    result = executor.execute(
        tool_name="github_get_pull_request",
        arguments={
            "owner": "test",
            "repo": "repo",
            "pull_number": 1,
        },
    )

    assert result == {
        "number": 1,
        "title": "Test PR",
    }

    client.call_tool.assert_called_once_with(
        tool_name="github_get_pull_request",
        arguments={
            "owner": "test",
            "repo": "repo",
            "pull_number": 1,
        },
    )


def test_denied_mcp_tool_blocks_execution():
    client = Mock()

    context = make_context()

    permission_service = make_permission_service()

    permission_service.set_workspace_plugins(
        workspace_id=1,
        plugins={"github"},
    )

    permission_service.set_workspace_tools(
        workspace_id=1,
        plugin_name="github",
        tools={"github_get_issue"},
    )

    registry = ToolRegistry()

    registry.register(
        make_mcp_tool(client)
    )

    executor = ToolExecutor(
        registry=registry,
        context=context,
        mcp_permission_service=permission_service,
    )

    with pytest.raises(PermissionError):
        executor.execute(
            tool_name="github_get_pull_request",
            arguments={
                "owner": "test",
                "repo": "repo",
                "pull_number": 1,
            },
        )

    client.call_tool.assert_not_called()


def test_request_scope_can_only_reduce_mcp_permission():
    client = Mock()

    context = make_context(
        allowed_tools=frozenset(),
    )

    permission_service = make_permission_service()

    permission_service.set_workspace_plugins(
        workspace_id=1,
        plugins={"github"},
    )

    registry = ToolRegistry()

    registry.register(
        make_mcp_tool(client)
    )

    executor = ToolExecutor(
        registry=registry,
        context=context,
        mcp_permission_service=permission_service,
    )

    with pytest.raises(PermissionError):
        executor.execute(
            tool_name="github_get_pull_request",
            arguments={
                "owner": "test",
                "repo": "repo",
                "pull_number": 1,
            },
        )

    client.call_tool.assert_not_called()


def test_request_scope_cannot_grant_denied_mcp_plugin():
    client = Mock()

    context = make_context(
        allowed_tools=frozenset({
            "github_get_pull_request",
        }),
    )

    executor = make_executor(
        context=context,
        client=client,
    )

    with pytest.raises(PermissionError):
        executor.execute(
            tool_name="github_get_pull_request",
            arguments={
                "owner": "test",
                "repo": "repo",
                "pull_number": 1,
            },
        )

    client.call_tool.assert_not_called()


def test_disabled_mcp_plugin_blocks_execution():
    client = Mock()

    plugin_registry = MCPPluginRegistry()

    plugin_registry.register(
        MCPPlugin(
            name="github",
            display_name="GitHub",
            server_config=MCPServerConfig(
                name="github",
                command="python",
            ),
            enabled=False,
        )
    )

    permission_service = MCPPermissionService(
        registry=plugin_registry,
    )

    permission_service.set_workspace_plugins(
        workspace_id=1,
        plugins={"github"},
    )

    context = make_context()

    registry = ToolRegistry()

    registry.register(
        make_mcp_tool(client)
    )

    executor = ToolExecutor(
        registry=registry,
        context=context,
        mcp_permission_service=permission_service,
    )

    with pytest.raises(PermissionError):
        executor.execute(
            tool_name="github_get_pull_request",
            arguments={
                "owner": "test",
                "repo": "repo",
                "pull_number": 1,
            },
        )

    client.call_tool.assert_not_called()
