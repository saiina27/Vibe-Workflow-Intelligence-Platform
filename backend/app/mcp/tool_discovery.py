from __future__ import annotations

import time

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

    # GitHub's hosted remote MCP server (api.githubcopilot.com)
    # returns a generic -32603 "Server returned an error
    # response" for every search_* tool (search_commits,
    # search_repositories, search_code, search_issues,
    # search_pull_requests, search_users), while the
    # direct get_*/list_* tools work reliably with the same
    # OAuth token. The model also keeps picking search_* tools
    # despite prompt instructions not to, so they are excluded
    # from registration entirely here rather than relying on
    # the LLM to avoid them.
    UNRELIABLE_GITHUB_TOOL_PREFIXES = (
        "search_commits",
    )

    # The tool list of a connected server rarely changes, so it is
    # kept on the (shared) client instead of being fetched for
    # every request. A reconnect creates a new client and cache.
    TOOLS_CACHE_SECONDS = 600

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

    def _is_tool_excluded(
        self,
        tool_name: str,
    ) -> bool:

        if self.plugin_name.lower() != "github":
            return False

        return tool_name.startswith(
            self.UNRELIABLE_GITHUB_TOOL_PREFIXES
        )

    async def discover(
        self,
        registry: ToolRegistry,
    ) -> int:
        """
        Discover all tools exposed by the MCP server.

        Returns:
            Number of tools successfully registered.
        """

        cached = getattr(self.client, "_tools_cache", None)
        now = time.monotonic()

        if (
            isinstance(cached, tuple)
            and len(cached) == 2
            and isinstance(cached[0], float)
            and now - cached[0] < self.TOOLS_CACHE_SECONDS
        ):
            tools = cached[1]

        else:
            tools = self.client.list_tools()

            try:
                self.client._tools_cache = (now, tools)
            except Exception:
                pass

            print(
                f"🔎 {self.plugin_name.capitalize()} MCP DISCOVERED TOOLS:",
                [tool.name for tool in tools],
            )

        excluded = [
            tool.name
            for tool in tools
            if self._is_tool_excluded(tool.name)
        ]

        if excluded:
            print(
                f"🚫 {self.plugin_name.capitalize()} MCP tools "
                f"excluded as unreliable on this server: "
                f"{excluded}"
            )

        registered = 0

        for tool in tools:

            if self._is_tool_excluded(tool.name):
                continue

            adapter = MCPToolAdapter(
                client=self.client,
                tool=tool,
                plugin_name=self.plugin_name,
            )

            registry.register(adapter)

            registered += 1

        return registered
