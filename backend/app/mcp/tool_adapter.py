from __future__ import annotations

from typing import Any

from mcp.types import Tool

from app.ai.tools.base import BaseTool
from app.mcp.client import MCPClient


class MCPToolAdapter(BaseTool):
    """
    Adapts one external MCP tool to Vibe's BaseTool contract.

    The adapter preserves the existing synchronous BaseTool
    interface.

    MCPClient internally owns the asynchronous MCP runtime,
    so the adapter never creates a second asyncio event loop.
    """

    def __init__(
        self,
        client: MCPClient,
        tool: Tool,
        plugin_name: str,
    ) -> None:
        if not plugin_name or not plugin_name.strip():
            raise ValueError(
                "MCP plugin name cannot be empty."
            )

        self._client = client
        self._tool = tool
        self._plugin_name = plugin_name.strip()

    # ========================================================
    # MCP PLUGIN IDENTITY
    # ========================================================

    @property
    def plugin_name(self) -> str:
        return self._plugin_name

    # ========================================================
    # TOOL METADATA
    # ========================================================

    @property
    def name(self) -> str:
        return self._tool.name

    @property
    def description(self) -> str:
        return self._tool.description or ""

    @property
    def parameters(self) -> dict[str, Any]:
        return dict(self._tool.input_schema)

    # ========================================================
    # EXECUTION
    # ========================================================

    def execute(
        self,
        **kwargs: Any,
    ) -> Any:
        """
        Execute the MCP tool.

        MCPClient guarantees that the actual asynchronous
        operation runs on the same event loop that owns the
        MCP connection.
        """

        return self._client.call_tool(
            tool_name=self.name,
            arguments=kwargs,
        )
