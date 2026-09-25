from abc import ABC, abstractmethod
from collections.abc import Iterator
from typing import Any

from app.schemas.ai import (
    AIRequest,
    AIResponse,
    AIStreamEvent,
)


class AIProvider(ABC):

    @abstractmethod
    def generate(
        self,
        request: AIRequest,
    ) -> AIResponse:
        pass

    @abstractmethod
    def generate_with_tools(
        self,
        request: AIRequest,
    ) -> AIResponse:
        """
        Generate a response using native provider
        tool/function calling.
        """
        pass

    @abstractmethod
    def generate_with_tool_results(
        self,
        request: AIRequest,
        original_response: AIResponse,
        tool_results: list[dict[str, Any]],
    ) -> AIResponse:
        """
        Generate the final response after tool execution.
        """
        pass

    @abstractmethod
    def stream(
        self,
        request: AIRequest,
    ) -> Iterator[str]:
        """
        Stream the AI response incrementally.

        Providers should yield text chunks as they
        become available.
        """
        pass

    @abstractmethod
    def stream_with_tools(
        self,
        request: AIRequest,
    ) -> Iterator[AIStreamEvent]:
        """
        Stream an AI response while supporting native
        provider tool calling.

        Providers should emit provider-independent
        AIStreamEvent objects for generated content
        and requested tool calls.
        """
        pass

    @abstractmethod
    def stream_with_tool_results(
        self,
        request: AIRequest,
        original_response: AIResponse,
        tool_results: list[dict[str, Any]],
    ) -> Iterator[AIStreamEvent]:
        """
        Stream the final AI response after tool execution.

        Providers should preserve the original provider
        context and emit provider-independent stream events
        as the final response becomes available.
        """
        pass
