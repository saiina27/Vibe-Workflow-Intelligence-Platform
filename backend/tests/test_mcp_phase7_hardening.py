from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.ai.tools.context import ToolContext
from app.ai.tools.registry import ToolRegistry
from app.ai.tools.router import ToolRouter
from app.mcp.integration_manager import MCPIntegrationManager
from app.mcp.registry import MCPPlugin, MCPPluginRegistry
from app.mcp.server_manager import (
    MCPServerConfig,
    MCPServerManager,
)
from app.mcp.tool_discovery import MCPToolDiscovery


# ============================================================
# HELPERS
# ============================================================


def make_plugin_registry():
    registry = MCPPluginRegistry()

    registry.register(
        MCPPlugin(
            name="github",
            display_name="GitHub",
            server_config=MCPServerConfig(
                name="github",
                command="python",
                args=("-m", "example"),
            ),
            enabled=True,
            auth_type="oauth",
        )
    )

    registry.register(
        MCPPlugin(
            name="slack",
            display_name="Slack",
            server_config=MCPServerConfig(
                name="slack",
                transport="streamable_http",
                url="https://example.com/mcp",
            ),
            enabled=True,
            auth_type="oauth",
        )
    )

    return registry


def make_manager():
    return MCPIntegrationManager(
        server_manager=MCPServerManager(),
        plugin_registry=make_plugin_registry(),
    )


# ============================================================
# MCP CORE HARDENING
# ============================================================


def test_server_manager_registers_server_only_once():
    manager = MCPServerManager()

    config = MCPServerConfig(
        name="github:1",
        command="python",
        args=("-m", "example"),
    )

    manager.register_server(config)

    assert manager.list_servers() == ["github:1"]

    with pytest.raises(ValueError):
        manager.register_server(config)


def test_server_manager_unknown_client_is_rejected():
    manager = MCPServerManager()

    with pytest.raises(
        RuntimeError,
        match="not connected",
    ):
        manager.get_client("github:1")


def test_server_manager_unknown_config_is_rejected():
    manager = MCPServerManager()

    with pytest.raises(
        ValueError,
        match="not registered",
    ):
        manager.get_config("github:1")


# ============================================================
# TOOL DISCOVERY
# ============================================================


@pytest.mark.asyncio
async def test_mcp_tool_discovery_registers_all_tools():
    client = MagicMock()

    tool_one = MagicMock()
    tool_one.name = "github_get_pull_request"
    tool_one.description = "Get pull request"
    tool_one.inputSchema = {
        "type": "object",
        "properties": {},
    }

    tool_two = MagicMock()
    tool_two.name = "github_get_issue"
    tool_two.description = "Get issue"
    tool_two.inputSchema = {
        "type": "object",
        "properties": {},
    }

    client.list_tools.return_value = [
        tool_one,
        tool_two,
    ]

    registry = ToolRegistry()

    discovery = MCPToolDiscovery(
        client=client,
        plugin_name="github",
    )

    count = await discovery.discover(registry)

    assert count == 2

    assert registry.get(
        "github_get_pull_request"
    ).plugin_name == "github"

    assert registry.get(
        "github_get_issue"
    ).plugin_name == "github"


@pytest.mark.asyncio
async def test_mcp_tool_discovery_propagates_client_failure():
    client = MagicMock()

    client.list_tools.side_effect = RuntimeError(
        "MCP server unavailable"
    )

    registry = ToolRegistry()

    discovery = MCPToolDiscovery(
        client=client,
        plugin_name="github",
    )

    with pytest.raises(
        RuntimeError,
        match="MCP server unavailable",
    ):
        await discovery.discover(registry)


# ============================================================
# GITHUB RUNTIME
# ============================================================


def test_github_runtime_name_is_user_scoped():
    manager = make_manager()

    assert (
        manager._get_github_runtime_name(42)
        == "github:42"
    )


def test_github_runtime_rejects_invalid_user():
    manager = make_manager()

    with pytest.raises(
        ValueError,
        match="User ID must be positive",
    ):
        manager._get_github_runtime_name(0)


def test_github_server_config_contains_read_only_settings():
    manager = make_manager()

    config = manager._build_github_server_config(
        runtime_name="github:42",
        access_token="secret-token",
    )

    assert config.name == "github:42"
    assert config.command == "docker"

    assert (
        "ghcr.io/github/github-mcp-server"
        in config.args
    )

    assert (
        config.env["GITHUB_PERSONAL_ACCESS_TOKEN"]
        == "secret-token"
    )

    assert config.env["GITHUB_READ_ONLY"] == "1"


def test_github_server_registration_is_idempotent():
    manager = make_manager()

    first = manager._register_github_server(
        user_id=42,
        access_token="token",
    )

    second = manager._register_github_server(
        user_id=42,
        access_token="token",
    )

    assert first == "github:42"
    assert second == "github:42"

    assert manager.server_manager.list_servers() == [
        "github:42"
    ]


@pytest.mark.asyncio
async def test_github_runtime_connects_and_discovers_tools():
    manager = make_manager()

    db = MagicMock()

    registry = ToolRegistry()

    with patch(
        "app.mcp.integration_manager."
        "external_integration_repository.get_integration"
    ) as get_integration, patch(
        "app.mcp.integration_manager.decrypt_token",
        return_value="github-token",
    ), patch.object(
        manager.server_manager,
        "connect",
        new=AsyncMock(),
    ) as connect:

        integration = MagicMock()
        integration.access_token = "encrypted-token"

        get_integration.return_value = integration

        client = MagicMock()
        connect.return_value = client

        with patch(
            "app.mcp.integration_manager.MCPToolDiscovery"
        ) as discovery_class:

            discovery = MagicMock()
            discovery.discover = AsyncMock(
                return_value=3
            )

            discovery_class.return_value = discovery

            count = await manager.connect_github(
                db=db,
                user_id=42,
                registry=registry,
            )

    assert count == 3

    connect.assert_awaited_once()

    discovery.discover.assert_awaited_once_with(
        registry
    )


# ============================================================
# SLACK RUNTIME
# ============================================================


def test_slack_runtime_name_is_user_scoped():
    manager = make_manager()

    assert (
        manager._get_slack_runtime_name(42)
        == "slack:42"
    )


def test_slack_runtime_rejects_invalid_user():
    manager = make_manager()

    with pytest.raises(
        ValueError,
        match="User ID must be positive",
    ):
        manager._get_slack_runtime_name(0)


def test_slack_server_requires_mcp_url():
    manager = make_manager()

    with patch(
        "app.mcp.integration_manager.settings.slack_mcp_url",
        "",
    ):
        with pytest.raises(
            RuntimeError,
            match="Slack MCP URL is not configured",
        ):
            manager._build_slack_server_config(
                "slack:42"
            )


def test_slack_server_uses_streamable_http():
    manager = make_manager()

    with patch(
        "app.mcp.integration_manager.settings.slack_mcp_url",
        "https://slack.example.com/mcp",
    ):
        config = manager._build_slack_server_config(
            "slack:42"
        )

    assert config.name == "slack:42"
    assert config.transport == "streamable_http"
    assert (
        config.url
        == "https://slack.example.com/mcp"
    )


# ============================================================
# DISCONNECT / CLEANUP
# ============================================================


@pytest.mark.asyncio
async def test_github_disconnect_uses_user_scoped_runtime():
    manager = make_manager()

    manager.server_manager.disconnect = AsyncMock()

    await manager.disconnect_github(
        user_id=42
    )

    manager.server_manager.disconnect.assert_awaited_once_with(
        "github:42"
    )


@pytest.mark.asyncio
async def test_slack_disconnect_uses_user_scoped_runtime():
    manager = make_manager()

    manager.server_manager.disconnect = AsyncMock()

    await manager.disconnect_slack(
        user_id=42
    )

    manager.server_manager.disconnect.assert_awaited_once_with(
        "slack:42"
    )


@pytest.mark.asyncio
async def test_disconnect_failure_is_not_silently_swallowed():
    manager = make_manager()

    manager.server_manager.disconnect = AsyncMock(
        side_effect=RuntimeError(
            "disconnect failed"
        )
    )

    with pytest.raises(
        RuntimeError,
        match="disconnect failed",
    ):
        await manager.disconnect_github(
            user_id=42
        )


# ============================================================
# INTEGRATION ERROR HANDLING
# ============================================================


def test_github_missing_integration_fails_cleanly():
    manager = make_manager()

    db = MagicMock()

    with patch(
        "app.mcp.integration_manager."
        "external_integration_repository.get_integration",
        return_value=None,
    ):
        with pytest.raises(
            RuntimeError,
            match="GitHub is not connected",
        ):
            manager._get_github_access_token(
                db=db,
                user_id=42,
            )


def test_slack_missing_integration_fails_cleanly():
    manager = make_manager()

    db = MagicMock()

    with patch(
        "app.mcp.integration_manager."
        "external_integration_repository.get_integration",
        return_value=None,
    ):
        with pytest.raises(
            RuntimeError,
            match="Slack is not connected",
        ):
            manager._get_slack_access_token(
                db=db,
                user_id=42,
            )


def test_github_token_decryption_failure_is_wrapped():
    manager = make_manager()

    db = MagicMock()

    integration = MagicMock()
    integration.access_token = "encrypted-token"

    with patch(
        "app.mcp.integration_manager."
        "external_integration_repository.get_integration",
        return_value=integration,
    ), patch(
        "app.mcp.integration_manager.decrypt_token",
        side_effect=Exception("bad encryption"),
    ):
        with pytest.raises(
            RuntimeError,
            match="Failed to decrypt GitHub access token",
        ):
            manager._get_github_access_token(
                db=db,
                user_id=42,
            )


# ============================================================
# MCP -> AI TOOL ROUTING
# ============================================================


@pytest.mark.asyncio
async def test_tool_router_builds_registry_with_native_tools():
    context = MagicMock(spec=ToolContext)

    context.user_id = 42
    context.db = MagicMock()

    router = ToolRouter()

    with patch.object(
        router.permission_service,
        "get_allowed_tools",
        return_value=[],
    ):
        registry = await router.build_registry(
            context
        )

    assert isinstance(
        registry,
        ToolRegistry,
    )


@pytest.mark.asyncio
async def test_tool_router_mcp_failure_does_not_crash_request():
    context = MagicMock(spec=ToolContext)

    context.user_id = 42
    context.db = MagicMock()

    router = ToolRouter()

    with patch.object(
        router.permission_service,
        "get_allowed_tools",
        return_value=["github"],
    ), patch.object(
        router.mcp_integration_manager,
        "connect_github",
        new=AsyncMock(
            side_effect=RuntimeError(
                "GitHub MCP unavailable"
            )
        ),
    ):

        registry = await router.build_registry(
            context
        )

    assert isinstance(
        registry,
        ToolRegistry,
    )