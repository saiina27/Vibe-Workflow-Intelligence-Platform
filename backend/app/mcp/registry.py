from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.mcp.server_manager import MCPServerConfig


@dataclass(frozen=True)
class MCPPlugin:
    """
    Provider-independent MCP plugin definition.

    A plugin represents an external integration exposed
    through an MCP server.

    Integration-specific behavior must remain outside
    the registry.
    """

    name: str
    display_name: str
    server_config: MCPServerConfig

    enabled: bool = True

    # Authentication metadata.
    #
    # Examples:
    #     "none"
    #     "oauth"
    #
    # The registry does not implement authentication.
    auth_type: str = "none"

    metadata: dict[str, Any] = field(
        default_factory=dict
    )


class MCPPluginRegistry:
    """
    Central registry for Vibe MCP plugins.

    Responsibilities:
        - Register MCP plugins.
        - Retrieve plugins.
        - Enable / disable plugins.
        - List registered plugins.
        - Resolve enabled plugins.

    This registry is intentionally integration-agnostic.

    GitHub, Slack, Notion, Jira, etc. are all represented
    using the same MCPPlugin contract.
    """

    def __init__(self) -> None:
        self._plugins: dict[str, MCPPlugin] = {}

    # ========================================================
    # REGISTER
    # ========================================================

    def register(
        self,
        plugin: MCPPlugin,
    ) -> None:
        """
        Register one MCP plugin.
        """

        name = plugin.name.strip()

        if not name:
            raise ValueError(
                "MCP plugin name cannot be empty."
            )

        if name in self._plugins:
            raise ValueError(
                f"MCP plugin '{name}' is already registered."
            )

        self._plugins[name] = plugin

    # ========================================================
    # GET
    # ========================================================

    def get(
        self,
        name: str,
    ) -> MCPPlugin:
        """
        Retrieve a registered MCP plugin.
        """

        plugin = self._plugins.get(name)

        if plugin is None:
            raise ValueError(
                f"MCP plugin '{name}' is not registered."
            )

        return plugin

    # ========================================================
    # LIST
    # ========================================================

    def list_plugins(self) -> list[MCPPlugin]:
        """
        Return every registered plugin.
        """

        return list(self._plugins.values())

    # ========================================================
    # ENABLED PLUGINS
    # ========================================================

    def list_enabled_plugins(self) -> list[MCPPlugin]:
        """
        Return only enabled plugins.
        """

        return [
            plugin
            for plugin in self._plugins.values()
            if plugin.enabled
        ]

    # ========================================================
    # ENABLE / DISABLE
    # ========================================================

    def enable(
        self,
        name: str,
    ) -> MCPPlugin:
        """
        Enable a registered plugin.

        Returns:
            Updated plugin definition.
        """

        plugin = self.get(name)

        updated = MCPPlugin(
            name=plugin.name,
            display_name=plugin.display_name,
            server_config=plugin.server_config,
            enabled=True,
            auth_type=plugin.auth_type,
            metadata=dict(plugin.metadata),
        )

        self._plugins[name] = updated

        return updated

    def disable(
        self,
        name: str,
    ) -> MCPPlugin:
        """
        Disable a registered plugin.

        Disabling a plugin does not disconnect an already
        active MCP server. Connection lifecycle remains the
        responsibility of MCPServerManager.
        """

        plugin = self.get(name)

        updated = MCPPlugin(
            name=plugin.name,
            display_name=plugin.display_name,
            server_config=plugin.server_config,
            enabled=False,
            auth_type=plugin.auth_type,
            metadata=dict(plugin.metadata),
        )

        self._plugins[name] = updated

        return updated

    # ========================================================
    # REMOVE
    # ========================================================

    def unregister(
        self,
        name: str,
    ) -> None:
        """
        Remove a registered plugin.

        Connection cleanup, if required, must be handled
        by MCPServerManager.
        """

        if name not in self._plugins:
            raise ValueError(
                f"MCP plugin '{name}' is not registered."
            )

        del self._plugins[name]

    # ========================================================
    # EXISTENCE
    # ========================================================

    def contains(
        self,
        name: str,
    ) -> bool:
        """
        Return whether a plugin is registered.
        """

        return name in self._plugins
