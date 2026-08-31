from app.mcp.integration_manager import (
    MCPIntegrationManager,
)
from app.mcp.registry import (
    MCPPlugin,
    MCPPluginRegistry,
)
from app.mcp.server_manager import (
    MCPServerConfig,
    MCPServerManager,
)
from app.core.config import settings
from app.mcp.permissions import (
    MCPPermissionService,
)


# ============================================================
# SHARED MCP RUNTIME
# ============================================================

mcp_server_manager = MCPServerManager()

mcp_plugin_registry = MCPPluginRegistry()

mcp_permission_service = MCPPermissionService(
    registry=mcp_plugin_registry,
)


# ============================================================
# GITHUB MCP PLUGIN
# ============================================================

github_plugin = MCPPlugin(
    name="github",
    display_name="GitHub",
    server_config=MCPServerConfig(
        name="github",
        command="docker",
    ),
    auth_type="oauth",
    metadata={
        "provider": "github",
        "capabilities": [
            "pull_requests",
            "issues",
            "commits",
            "development_context",
        ],
    },
)

mcp_plugin_registry.register(
    github_plugin
)


# ============================================================
# SLACK MCP PLUGIN
# ============================================================

slack_plugin = MCPPlugin(
    name="slack",
    display_name="Slack",
    server_config=MCPServerConfig(
        name="slack",
        transport="streamable_http",
        url=settings.slack_mcp_url,
    ),
    auth_type="oauth",
    metadata={
        "provider": "slack",
        "capabilities": [
            "search",
            "conversations",
            "developer_context",
            "team_questions",
        ],
    },
)

mcp_plugin_registry.register(
    slack_plugin
)


# ============================================================
# INTEGRATION MANAGER
# ============================================================

mcp_integration_manager = MCPIntegrationManager(
    server_manager=mcp_server_manager,
    plugin_registry=mcp_plugin_registry,
)