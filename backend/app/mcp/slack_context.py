from __future__ import annotations

from typing import Any

from app.mcp.slack_conversation_retriever import (
    SlackConversationRetriever,
)


class SlackContextRetriever:
    """
    Builds bounded Slack context for developer/team questions.

    This composes the existing Slack conversation retrieval
    layer without introducing another MCP transport or client.
    """

    MAX_CONTEXT_CHARS = 8000

    def __init__(
        self,
        conversation_retriever: SlackConversationRetriever,
    ) -> None:
        self._conversation_retriever = conversation_retriever

    def retrieve(
        self,
        question: str,
        limit: int = 10,
    ) -> str:
        """
        Retrieve Slack context relevant to a developer/team
        question.
        """

        if not isinstance(question, str) or not question.strip():
            raise ValueError(
                "Developer/team question cannot be empty."
            )

        result = self._conversation_retriever.retrieve(
            query=question.strip(),
            limit=limit,
        )

        return self._bound_context(result)

    def _bound_context(
        self,
        result: Any,
    ) -> str:
        """
        Convert retrieved Slack data into bounded text
        suitable for AI context.
        """

        if result is None:
            return ""

        if isinstance(result, str):
            context = result

        elif isinstance(result, dict):
            context = str(
                result.get("results", result)
            )

        else:
            context = str(result)

        return context[: self.MAX_CONTEXT_CHARS]