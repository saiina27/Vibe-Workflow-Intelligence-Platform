from __future__ import annotations

from app.ai.tools.registry import ToolRegistry
from app.mcp.client import MCPClient
from app.mcp.tool_adapter import MCPToolAdapter


class MCPToolDiscovery:
    """
    Discovers tools exposed by an MCP server and adapts them
    into Vibe's ToolRegistry.

    Plugin identity is preserved on every adapter so the
    authorization layer can enforce plugin/tool permissions.
    """

    def __init__(
        self,
        client: MCPClient,
        plugin_name: str,
    ) -> None:
        if not plugin_name or not plugin_name.strip():
            raise ValueError(
                "MCP plugin name cannot be empty."
            )

        self.client = client
        self.plugin_name = plugin_name.strip()

    async def discover(
        self,
        registry: ToolRegistry,
    ) -> int:
        """
        Discover all tools exposed by the MCP server.

        Returns:
            Number of tools successfully registered.
        """

        tools = self.client.list_tools()

        registered = 0

        for tool in tools:
            adapter = MCPToolAdapter(
                client=self.client,
                tool=tool,
                plugin_name=self.plugin_name,
            )

            registry.register(adapter)

            registered += 1

        return registered
