import pytest

from app.ai.tools.context import ToolContext
from app.mcp.permissions import MCPPermissionService
from app.mcp.registry import (
    MCPPlugin,
    MCPPluginRegistry,
)
from app.mcp.server_manager import MCPServerConfig


def make_registry(
    enabled=True,
):
    registry = MCPPluginRegistry()

    registry.register(
        MCPPlugin(
            name="github",
            display_name="GitHub",
            server_config=MCPServerConfig(
                name="github",
                command="python",
            ),
            enabled=enabled,
        )
    )

    return registry


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


def test_plugin_is_denied_by_default():
    service = MCPPermissionService(
        make_registry()
    )

    context = make_context()

    assert service.is_plugin_allowed(
        "github",
        context,
    ) is False


def test_workspace_can_allow_plugin():
    service = MCPPermissionService(
        make_registry()
    )

    service.set_workspace_plugins(
        workspace_id=1,
        plugins={"github"},
    )

    context = make_context(
        workspace_id=1,
    )

    assert service.is_plugin_allowed(
        "github",
        context,
    ) is True


def test_user_can_allow_plugin():
    service = MCPPermissionService(
        make_registry()
    )

    service.set_user_plugins(
        user_id=10,
        plugins={"github"},
    )

    context = make_context(
        workspace_id=99,
        user_id=10,
    )

    assert service.is_plugin_allowed(
        "github",
        context,
    ) is True


def test_workspace_plugin_policy_overrides_user_policy():
    service = MCPPermissionService(
        make_registry()
    )

    service.set_workspace_plugins(
        workspace_id=1,
        plugins=set(),
    )

    service.set_user_plugins(
        user_id=1,
        plugins={"github"},
    )

    context = make_context(
        workspace_id=1,
        user_id=1,
    )

    assert service.is_plugin_allowed(
        "github",
        context,
    ) is False


def test_disabled_plugin_is_denied():
    service = MCPPermissionService(
        make_registry(enabled=False)
    )

    service.set_workspace_plugins(
        workspace_id=1,
        plugins={"github"},
    )

    context = make_context()

    assert service.is_plugin_allowed(
        "github",
        context,
    ) is False


def test_unknown_plugin_is_denied():
    service = MCPPermissionService(
        make_registry()
    )

    service.set_workspace_plugins(
        workspace_id=1,
        plugins={"slack"},
    )

    context = make_context()

    assert service.is_plugin_allowed(
        "slack",
        context,
    ) is False


def test_plugin_permission_allows_tool():
    service = MCPPermissionService(
        make_registry()
    )

    service.set_workspace_plugins(
        workspace_id=1,
        plugins={"github"},
    )

    context = make_context()

    assert service.is_tool_allowed(
        "github",
        "github_get_pull_request",
        context,
    ) is True


def test_workspace_tool_permission_restricts_tool():
    service = MCPPermissionService(
        make_registry()
    )

    service.set_workspace_plugins(
        workspace_id=1,
        plugins={"github"},
    )

    service.set_workspace_tools(
        workspace_id=1,
        plugin_name="github",
        tools={"github_get_pull_request"},
    )

    context = make_context()

    assert service.is_tool_allowed(
        "github",
        "github_get_pull_request",
        context,
    ) is True

    assert service.is_tool_allowed(
        "github",
        "github_get_issue",
        context,
    ) is False


def test_user_tool_permission_is_used_without_workspace_override():
    service = MCPPermissionService(
        make_registry()
    )

    service.set_user_plugins(
        user_id=10,
        plugins={"github"},
    )

    service.set_user_tools(
        user_id=10,
        plugin_name="github",
        tools={"github_get_issue"},
    )

    context = make_context(
        workspace_id=99,
        user_id=10,
    )

    assert service.is_tool_allowed(
        "github",
        "github_get_issue",
        context,
    ) is True

    assert service.is_tool_allowed(
        "github",
        "github_get_pull_request",
        context,
    ) is False


def test_context_restriction_can_only_reduce_permission():
    service = MCPPermissionService(
        make_registry()
    )

    service.set_workspace_plugins(
        workspace_id=1,
        plugins={"github"},
    )

    context = make_context(
        allowed_tools=frozenset({
            "github_get_pull_request",
        }),
    )

    assert service.is_tool_allowed(
        "github",
        "github_get_pull_request",
        context,
    ) is True

    assert service.is_tool_allowed(
        "github",
        "github_get_issue",
        context,
    ) is False


def test_context_restriction_cannot_grant_permission():
    service = MCPPermissionService(
        make_registry()
    )

    service.set_workspace_plugins(
        workspace_id=1,
        plugins=set(),
    )

    context = make_context(
        allowed_tools=frozenset({
            "github_get_pull_request",
        }),
    )

    assert service.is_tool_allowed(
        "github",
        "github_get_pull_request",
        context,
    ) is False
