
from __future__ import annotations

from typing import Any

from app.ai.tools.base import BaseTool
from app.mcp.client import MCPClient


class SlackSearchTool(BaseTool):
    """
    Vibe-facing Slack search tool.

    Searches Slack public channels through the connected
    Slack MCP server.

    Private-channel / DM search is intentionally not exposed
    here because the Slack MCP server requires explicit user
    consent for that operation.
    """

    def __init__(
        self,
        client: MCPClient,
    ) -> None:
        self._client = client

    # ========================================================
    # MCP PLUGIN IDENTITY
    # ========================================================

    @property
    def plugin_name(self) -> str:
        """
        Identify the external MCP plugin that owns this tool.

        This keeps the Slack bridge compatible with Vibe's
        plugin-aware permission and authorization layer.
        """

        return "slack"

    # ========================================================
    # TOOL METADATA
    # ========================================================

    @property
    def name(self) -> str:
        return "slack_search"

    @property
    def description(self) -> str:
        return (
            "Search messages in public Slack channels. "
            "Use Slack search syntax such as "
            "'bug report', 'in:engineering', "
            "'from:@username', 'after:2026-01-01'. "
            "Returns matching Slack messages and optional "
            "surrounding context."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": (
                        "Slack search query. "
                        "Supports keywords and Slack search "
                        "modifiers such as in:, from:, to:, "
                        "after:, before:, is:thread, has:file."
                    ),
                },
                "limit": {
                    "type": "integer",
                    "description": (
                        "Maximum number of search results. "
                        "Maximum 20."
                    ),
                    "default": 20,
                },
                "sort": {
                    "type": "string",
                    "description": (
                        "Sort results by relevance or timestamp."
                    ),
                    "default": "score",
                },
                "sort_dir": {
                    "type": "string",
                    "description": (
                        "Sort direction: asc or desc."
                    ),
                    "default": "desc",
                },
                "include_context": {
                    "type": "boolean",
                    "description": (
                        "Include surrounding Slack messages "
                        "for each result."
                    ),
                    "default": True,
                },
                "max_context_length": {
                    "type": "integer",
                    "description": (
                        "Maximum character length for each "
                        "surrounding context message."
                    ),
                    "default": 3000,
                },
                "include_bots": {
                    "type": "boolean",
                    "description": (
                        "Whether bot messages should be included."
                    ),
                    "default": False,
                },
                "only_my_channels": {
                    "type": "boolean",
                    "description": (
                        "Limit results to public channels "
                        "the user is a member of."
                    ),
                    "default": False,
                },
            },
            "required": ["query"],
        }

    # ========================================================
    # EXECUTION
    # ========================================================

    def execute(
        self,
        **kwargs: Any,
    ) -> Any:
        """
        Execute Slack public-channel search through MCP.
        """

        query = kwargs.get("query")

        if not isinstance(query, str) or not query.strip():
            raise ValueError(
                "Slack search query cannot be empty."
            )

        arguments: dict[str, Any] = {
            "query": query.strip(),
        }

        optional_fields = (
            "limit",
            "sort",
            "sort_dir",
            "include_context",
            "max_context_length",
            "include_bots",
            "only_my_channels",
        )

        for field in optional_fields:
            if field in kwargs and kwargs[field] is not None:
                arguments[field] = kwargs[field]

        return self._client.call_tool(
            tool_name="slack_search_public",
            arguments=arguments,
        )
