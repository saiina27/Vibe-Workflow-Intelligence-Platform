from abc import ABC, abstractmethod
from typing import Any

from app.schemas.ai import AIRequest, AIResponse


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
