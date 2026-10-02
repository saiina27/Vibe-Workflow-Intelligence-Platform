from collections.abc import Iterator

from app.ai.providers.registry import ProviderRegistry
from app.ai.routing_decision import build_routing_decision
from app.schemas.ai import AIRequest, AIResponse, AIStreamEvent
from app.core.config import settings
from app.ai.retry import ai_retry


class ProviderRouter:

    def __init__(self):

        self.registry = ProviderRegistry()

        self.primary = self.registry.get_provider(
            settings.primary_provider
        )

        self.fallback = None

        if settings.fallback_provider:

            self.fallback = (
                self.registry.providers.get(
                    settings.fallback_provider
                )
            )

    def _get_model_for_provider(
        self,
        provider_name: str,
    ) -> str:
        """
        Return the configured model for a provider.
        """

        if provider_name == "gemini":

            return settings.gemini_model

        if provider_name == "groq":

            if not settings.groq_model:
                raise ValueError(
                    "GROQ_MODEL is not configured."
                )

            return settings.groq_model

        raise ValueError(
            f"Unsupported provider: {provider_name}"
        )

    def _select_provider(
        self,
        request: AIRequest,
    ):
        """
        Build routing decision and select provider.
        """

        decision = build_routing_decision(
            request.task_type,
            request.complexity,
        )

        # GitHub MCP tool calls use structured query syntax
        # (e.g. "owner:name/repo") that Groq's smaller fallback
        # model frequently fails to encode as valid JSON
        # arguments. Prefer Gemini for these specific tool
        # calls, even though technical tasks otherwise default
        # to Groq to conserve Gemini's free-tier quota.
        github_tool_requested = any(
            "github" in tool.name.lower()
            or tool.name
            in {
                "search_repositories",
                "search_code",
                "search_commits",
                "search_issues",
                "search_pull_requests",
                "search_users",
                "get_me",
                "get_commit",
                "list_commits",
                "list_branches",
                "list_issues",
                "list_pull_requests",
                "list_releases",
                "list_tags",
            }
            for tool in (request.tools or [])
        )

        if github_tool_requested and "gemini" in (
            self.registry.providers
        ):

            decision.provider = "gemini"
            decision.reason += (
                " (overridden: GitHub tool call, "
                "preferring Gemini for reliable JSON "
                "arguments)"
            )

        provider = self.registry.providers.get(
            decision.provider
        )

        if provider is None:

            print(
                f"Configured routing provider "
                f"'{decision.provider}' is unavailable."
            )

            provider = self.primary

            provider_name = settings.primary_provider

            request.model = self._get_model_for_provider(
                provider_name
            )

        else:

            provider_name = decision.provider

            request.model = self._get_model_for_provider(
                provider_name
            )

        print("=" * 60)
        print("AI ROUTING DECISION")
        print(
            f"Task: {decision.task_type.value}"
        )
        print(
            f"Complexity: {decision.complexity.value}"
        )
        print(
            f"Provider: {provider_name}"
        )
        print(
            f"Model: {request.model}"
        )
        print(
            f"Reason: {decision.reason}"
        )
        print("=" * 60)

        return provider

    def _switch_to_fallback(
        self,
        request: AIRequest,
    ):
        """
        Switch request configuration to fallback provider.
        """

        if self.fallback is None:

            raise RuntimeError(
                "Fallback provider is not configured."
            )

        fallback_name = settings.fallback_provider

        if fallback_name is None:

            raise RuntimeError(
                "Fallback provider name is missing."
            )

        request.model = self._get_model_for_provider(
            fallback_name
        )

        print("=" * 60)
        print("AI PROVIDER FALLBACK")
        print(
            f"Fallback Provider: {fallback_name}"
        )
        print(
            f"Fallback Model: {request.model}"
        )
        print("=" * 60)

        return self.fallback

    def generate(
        self,
        request: AIRequest,
    ) -> AIResponse:

        provider = self._select_provider(
            request
        )

        try:

            return provider.generate(
                request
            )

        except Exception as primary_error:

            print(
                f"Primary provider failed: "
                f"{primary_error}"
            )

            if self.fallback is None:

                raise

            fallback_provider = (
                self._switch_to_fallback(
                    request
                )
            )

            return fallback_provider.generate(
                request
            )

    def generate_with_tools(
        self,
        request: AIRequest,
    ) -> AIResponse:
        """
        Route a tool-enabled request through
        the selected AI provider.

        Flow:

            Router
                ↓
            Selected Provider
                ↓
            Tool Call
                ↓
            ToolCallingService
        """

        if not request.tools:

            raise ValueError(
                "Tool-enabled generation requires "
                "at least one tool."
            )

        provider = self._select_provider(
            request
        )

        try:

            return provider.generate_with_tools(
                request
            )

        except Exception as primary_error:

            print(
                "Primary tool-calling provider failed: "
                f"{primary_error}"
            )

            if self.fallback is None:

                raise

            fallback_provider = (
                self._switch_to_fallback(
                    request
                )
            )

            return fallback_provider.generate_with_tools(
                request
            )

    def stream(
        self,
        request: AIRequest,
    ) -> Iterator[str]:
        """
        Stream the AI response incrementally.

        Flow:

            AIRequest
                ↓
            ProviderRouter
                ↓
            Selected Provider
                ↓
            Provider.stream()
                ↓
            text chunk
                ↓
            text chunk
                ↓
            text chunk

        The router keeps the same provider-selection
        and fallback architecture used by normal
        generation.
        """

        provider = self._select_provider(
            request
        )

        try:

            yield from provider.stream(
                request
            )

        except Exception as primary_error:

            print(
                f"Primary streaming provider failed: "
                f"{primary_error}"
            )

            if self.fallback is None:

                raise

            fallback_provider = (
                self._switch_to_fallback(
                    request
                )
            )

            yield from fallback_provider.stream(
                request
            )

    def stream_with_tools(
        self,
        request: AIRequest,
    ) -> Iterator[AIStreamEvent]:
        """
        Stream an AI response while supporting native
        provider tool calling.

        The selected provider emits provider-independent
        AIStreamEvent objects.
        """

        if not request.tools:
            raise ValueError(
                "Tool-enabled streaming requires "
                "at least one tool."
            )

        provider = self._select_provider(
            request
        )

        try:
            yield from provider.stream_with_tools(
                request
            )

        except Exception as primary_error:

            print(
                "Primary tool-calling streaming "
                f"provider failed: {primary_error}"
            )

            if self.fallback is None:
                raise

            fallback_provider = (
                self._switch_to_fallback(
                    request
                )
            )

            yield from fallback_provider.stream_with_tools(
                request
            )

    @ai_retry
    def stream_with_tool_results(
        self,
        request: AIRequest,
        original_response: AIResponse,
        tool_results: list[dict],
    ) -> Iterator[AIStreamEvent]:
        """
        Stream the response after tool execution.

        The response is routed back to the SAME provider
        that generated the original tool call.
        """

        provider_name = (
            original_response.provider
        )

        provider = self.registry.providers.get(
            provider_name
        )

        if provider is None:
            raise ValueError(
                f"Provider '{provider_name}' not found "
                "for streaming tool-result round-trip."
            )

        request.model = self._get_model_for_provider(
            provider_name
        )

        print("=" * 60)
        print("AI STREAMING TOOL RESULT ROUTING")
        print(
            f"Provider: {provider_name}"
        )
        print(
            f"Model: {request.model}"
        )
        print(
            f"Tool Results: {len(tool_results)}"
        )
        print("=" * 60)

        yield from provider.stream_with_tool_results(
            request=request,
            original_response=original_response,
            tool_results=tool_results,
        )

    @ai_retry
    def generate_with_tool_results(
        self,
        request: AIRequest,
        original_response: AIResponse,
        tool_results: list[dict],
    ) -> AIResponse:
        """
        Send executed tool results back to the SAME
        provider that generated the original tool call.

        This is critical for native provider
        tool-calling round trips.
        """

        provider_name = (
            original_response.provider
        )

        provider = self.registry.providers.get(
            provider_name
        )

        if provider is None:

            raise ValueError(
                f"Provider '{provider_name}' not found "
                "for tool-result round-trip."
            )

        # Restore the model belonging to the provider
        # that originally generated the tool call.
        request.model = self._get_model_for_provider(
            provider_name
        )

        print("=" * 60)
        print("AI TOOL RESULT ROUTING")
        print(
            f"Provider: {provider_name}"
        )
        print(
            f"Model: {request.model}"
        )
        print(
            f"Tool Results: {len(tool_results)}"
        )
        print("=" * 60)

        return provider.generate_with_tool_results(
            request=request,
            original_response=original_response,
            tool_results=tool_results,
        )