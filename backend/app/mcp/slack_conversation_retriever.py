from __future__ import annotations

import json
from typing import Any

from app.mcp.client import MCPClient


class SlackConversationRetriever:
    """
    Retrieves relevant Slack conversations using the
    Slack MCP search capability.

    The Slack MCP search tool can return surrounding
    conversation context with each matching result.
    """

    MCP_TOOL_NAME = "slack_search_public"

    def __init__(
        self,
        client: MCPClient,
    ) -> None:
        self._client = client

    def retrieve(
        self,
        query: str,
        limit: int = 10,
    ) -> Any:
        """
        Search Slack and retrieve relevant conversation
        context around matching messages.
        """

        if not isinstance(query, str) or not query.strip():
            raise ValueError(
                "Slack conversation query cannot be empty."
            )

        if limit <= 0:
            raise ValueError(
                "Slack conversation limit must be positive."
            )

        result = self._client.call_tool(
            tool_name=self.MCP_TOOL_NAME,
            arguments={
                "query": query.strip(),
                "limit": min(limit, 20),
                "include_context": True,
            },
        )

        return self._parse_result(result)

    @staticmethod
    def _parse_result(
        result: Any,
    ) -> Any:
        """
        Normalize the MCP response when the server returns
        JSON inside TextContent.
        """

        if getattr(result, "is_error", False):
            raise RuntimeError(
                "Slack MCP conversation retrieval failed."
            )

        content = getattr(result, "content", None)

        if not content:
            return result

        for item in content:
            text = getattr(item, "text", None)

            if not text:
                continue

            try:
                return json.loads(text)
            except (TypeError, json.JSONDecodeError):
                return text

        return result