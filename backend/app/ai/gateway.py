from app.ai.prompt_cache import prompt_cache
from app.ai.router import ProviderRouter
from app.ai.retry import ai_retry
from app.ai.tool_calling import ToolCallingService
from app.ai.usage_metrics import usage_metrics
from app.schemas.ai import AIRequest, AIResponse
from app.ai.tools.context import ToolContext
from app.ai.tools.router import ToolRouter


class AIGateway:

    def __init__(self):

        self.provider = ProviderRouter()

        # ToolRouter builds a request-scoped
        # ToolRegistry using application-controlled context.
        self.tool_router = ToolRouter()

    # ========================================================
    # NORMAL PROVIDER CALL
    # ========================================================

    @ai_retry
    def _call_provider(
        self,
        request: AIRequest,
    ) -> AIResponse:

        return self.provider.generate(
            request
        )

    # ========================================================
    # NORMAL GENERATION
    # ========================================================

    def generate(
        self,
        request: AIRequest,
    ) -> AIResponse:

        cached_response = prompt_cache.get(
            request.prompt
        )

        if cached_response is not None:

            print("✅ Prompt Cache Hit")

            return AIResponse(
                content=cached_response,
                model="cache",
                provider="cache",
            )

        try:

            ai_response = self._call_provider(
                request
            )

            usage_metrics.record(
                ai_response
            )

            if ai_response.content is not None:

                prompt_cache.set(
                    prompt=request.prompt,
                    response=ai_response.content,
                )

            return ai_response

        except Exception as e:

            print(
                f"AI Gateway Error: {e}"
            )

            raise

    # ========================================================
    # TOOL-CALLING PROVIDER CALL
    # ========================================================

    @ai_retry
    def _call_provider_with_tools(
        self,
        request: AIRequest,
    ) -> AIResponse:

        return self.provider.generate_with_tools(
            request
        )

    # ========================================================
    # TOOL-CALLING ENTRY POINT
    # ========================================================

    def generate_with_tools(
        self,
        request: AIRequest,
        context: ToolContext,
    ) -> AIResponse:
        """
        Sprint 11 tool-calling entry point.

        Each request receives its own ToolRegistry.

        Flow:

            Gateway
                ↓
            ToolRouter
                ↓
            Request-scoped ToolRegistry
                ↓
            ProviderRouter
                ↓
            AI Provider
                ↓
            Tool Call
                ↓
            ToolCallingService
                ↓
            ToolExecutor
                ↓
            Tool Result
                ↓
            SAME Provider
                ↓
            Final Answer
        """

        # ====================================================
        # STEP 1: Build request-scoped registry
        # ====================================================

        registry = self.tool_router.build_registry(
            context
        )

        # ====================================================
        # STEP 2: Convert registered tools into
        # provider-independent tool definitions
        # ====================================================

        request.tools = registry.definitions()

        if not request.tools:

            raise ValueError(
                "No tools are registered for this request."
            )

        # ====================================================
        # STEP 3: Create request-scoped ToolCallingService
        # ====================================================

        tool_calling = ToolCallingService(
            registry=registry,
            provider=self.provider,
            context=context,
        )

        try:

            # =================================================
            # STEP 4: Initial provider request
            # =================================================

            initial_response = (
                self._call_provider_with_tools(
                    request
                )
            )

            usage_metrics.record(
                initial_response
            )

            # =================================================
            # STEP 5: Provider answered directly
            # =================================================

            if not initial_response.tool_calls:

                return initial_response

            # =================================================
            # STEP 6: Tool call detected
            # =================================================

            print(
                "🔧 Tool calling requested."
            )

            print(
                f"🔧 Tool calls: "
                f"{len(initial_response.tool_calls)}"
            )

            for tool_call in initial_response.tool_calls:

                print(
                    f"🔧 Tool name: "
                    f"{tool_call.name}"
                )

                print(
                    f"🔧 Tool arguments: "
                    f"{tool_call.arguments}"
                )

            # =================================================
            # STEP 7: Execute tools and complete
            # provider round-trip
            # =================================================

            final_response = (
                tool_calling
                .complete_with_tool_results(
                    request=request,
                    initial_response=initial_response,
                )
            )

            usage_metrics.record(
                final_response
            )

            # =================================================
            # STEP 8: Validate final response
            # =================================================

            if final_response.content is None:

                raise RuntimeError(
                    "AI provider returned no final "
                    "content after tool execution."
                )

            return final_response

        except Exception as e:

            print(
                f"AI Gateway Tool Calling Error: {e}"
            )

            raise