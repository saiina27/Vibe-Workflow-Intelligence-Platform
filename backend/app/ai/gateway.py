from collections.abc import Iterator

from app.ai.prompt_cache import prompt_cache
from app.ai.router import ProviderRouter
from app.ai.retry import ai_retry
from app.ai.tool_calling import ToolCallingService
from app.ai.usage_metrics import usage_metrics
from app.schemas.ai import (
    AIRequest,
    AIResponse,
    AIStreamEvent,
)
from app.ai.tools.context import ToolContext
from app.ai.tools.router import ToolRouter
from app.mcp.runtime import (
    mcp_permission_service,
)


UNEXPOSED_TOOL_MESSAGE = (
    "I couldn't complete that request because I tried to use a tool "
    "that isn't available for this question. Please rephrase it "
    "(for example, mention the repository name) and try again."
)


INVALID_TOOL_ARGS_MESSAGE = (
    "I couldn't complete that request because the tool was called "
    "with invalid arguments. Please try asking again."
)


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
    # NORMAL STREAMING PROVIDER CALL
    # ========================================================

    def stream(
        self,
        request: AIRequest,
    ) -> Iterator[str]:
        """
        Stream the AI response incrementally.

        Streaming intentionally bypasses prompt cache.
        """

        try:

            yield from self.provider.stream(
                request
            )

        except Exception as e:

            print(
                f"AI Gateway Streaming Error: {e}"
            )

            raise

    # ========================================================
    # STREAMING TOOL-CALLING PROVIDER CALL
    # ========================================================

    @ai_retry
    def _stream_provider_with_tools(
        self,
        request: AIRequest,
    ) -> Iterator[AIStreamEvent]:

        yield from self.provider.stream_with_tools(
            request
        )

    @ai_retry
    def _stream_provider_with_tool_results(
        self,
        request: AIRequest,
        original_response: AIResponse,
        tool_results: list[dict],
    ) -> Iterator[AIStreamEvent]:

        yield from self.provider.stream_with_tool_results(
            request=request,
            original_response=original_response,
            tool_results=tool_results,
        )

    @staticmethod
    def _guard_unexposed_tool_errors(events):
        """
        If the provider rejects a tool call that was not in
        request.tools, end the stream with a clear message
        instead of crashing the whole chat.
        """

        try:
            yield from events

        except Exception as exc:
            text = str(exc).lower()

            if (
                "not in request.tools" in text
                or "tool call validation failed" in text
            ):
                print(
                    "🚫 Provider rejected a tool call: "
                    f"{exc}"
                )

                message = (
                    UNEXPOSED_TOOL_MESSAGE
                    if "not in request.tools" in text
                    else INVALID_TOOL_ARGS_MESSAGE
                )

                yield AIStreamEvent(
                    type="content",
                    text=message,
                )

                return

            raise

    # ========================================================
    # STREAMING TOOL-CALLING REGISTRY
    # ========================================================

    def _build_streaming_registry(
        self,
        context: ToolContext,
    ):
        """
        Build the request-scoped registry for the synchronous
        streaming generator.

        ToolRouter exposes an async registry builder, while
        the current provider streaming interface is
        synchronous.

        The SSE route currently invokes this synchronous
        generator from a synchronous request handler, so
        asyncio.run() is used when no event loop is active.
        """

        import asyncio

        try:
            asyncio.get_running_loop()

        except RuntimeError:

            return asyncio.run(
                self.tool_router.build_registry(
                    context
                )
            )

        raise RuntimeError(
            "Cannot build the streaming tool registry while "
            "an asyncio event loop is already running."
        )

    # ========================================================
    # STREAMING TOOL-CALLING ENTRY POINT
    # ========================================================

    def stream_with_tools(
        self,
        request: AIRequest,
        context: ToolContext,
    ) -> Iterator[AIStreamEvent]:
        """
        Provider-independent streaming tool orchestration.

        Flow:

            Provider
                ↓
            content / tool_call
                ↓
            ToolCallingService
                ↓
            tool_start
                ↓
            REAL ToolExecutor execution
                ↓
            ToolCallLog
                ↓
            tool_done / tool_error
                ↓
            tool_result
                ↓
            SAME provider
                ↓
            final content

        Multiple provider → tool → provider rounds are
        supported up to ToolCallingService.MAX_TOOL_ITERATIONS.

        Tool lifecycle events are emitted directly from the
        streaming execution path so the frontend can observe
        the real order:

            tool_start
            → execution
            → tool_done / tool_error
        """

        # ====================================================
        # STEP 1: BUILD REQUEST-SCOPED TOOL REGISTRY
        # ====================================================

        registry = self._build_streaming_registry(
            context
        )

        # ====================================================
        # STEP 2: ATTACH TOOL DEFINITIONS
        # ====================================================

        request.tools = registry.definitions_for_prompt(request.prompt)

        if not request.tools:

            raise ValueError(
                "No tools are registered for this request."
            )

        exposed_names = {tool.name for tool in request.tools}

        # ====================================================
        # STEP 3: CREATE REQUEST-SCOPED TOOL SERVICE
        # ====================================================

        tool_calling = ToolCallingService(
            registry=registry,
            provider=self.provider,
            context=context,
            mcp_permission_service=mcp_permission_service,
        )

        # ====================================================
        # STEP 4: INITIAL PROVIDER STREAM
        # ====================================================

        provider_events = self._guard_unexposed_tool_errors(
            self._stream_provider_with_tools(request)
        )

        # ====================================================
        # STEP 5: PROVIDER / TOOL ITERATION LOOP
        # ====================================================

        for iteration in range(
            1,
            tool_calling.MAX_TOOL_ITERATIONS + 1,
        ):

            print("=" * 60)

            print(
                "AI STREAMING TOOL-CALLING ITERATION"
            )

            print(
                f"Iteration: "
                f"{iteration}/"
                f"{tool_calling.MAX_TOOL_ITERATIONS}"
            )

            print("=" * 60)

            tool_call_detected = False

            # Provider context must be preserved when the
            # provider requests tools.
            current_response: AIResponse | None = None

            # =================================================
            # STREAM CURRENT PROVIDER RESPONSE
            # =================================================

            for event in provider_events:

                # ---------------------------------------------
                # NORMAL CONTENT
                # ---------------------------------------------

                if event.type == "content":

                    yield event

                    continue

                # ---------------------------------------------
                # PROVIDER TOOL CALL
                # ---------------------------------------------

                if event.type == "tool_call":

                    if not event.tool_calls:

                        raise RuntimeError(
                            "Provider emitted a tool_call "
                            "event without tool calls."
                        )

                    tool_call_detected = True

                    current_response = AIResponse(
                        content=None,
                        model=event.model,
                        provider=event.provider,
                        tool_calls=event.tool_calls,
                        provider_context=(
                            event.provider_context
                        ),
                    )

                    print(
                        "🔧 Streaming tool calling requested."
                    )

                    print(
                        f"🔧 Tool calls: "
                        f"{len(event.tool_calls)}"
                    )

                    for tool_call in event.tool_calls:
                        print(
                            f"🔧 Tool name: "
                            f"{tool_call.name}"
                        )
                        print(
                            f"🔧 Tool arguments: "
                            f"{tool_call.arguments}"
                        )

                    # -----------------------------------------
                    # REAL STREAMING TOOL EXECUTION
                    # -----------------------------------------

                    blocked_tools = [
                        tc.name
                        for tc in event.tool_calls
                        if tc.name not in exposed_names
                    ]

                    if blocked_tools:
                        print(
                            "🚫 Blocked tool call(s) not exposed "
                            f"to the model: {blocked_tools}"
                        )

                        yield AIStreamEvent(
                            type="content",
                            text=UNEXPOSED_TOOL_MESSAGE,
                        )

                        return

                    tool_results = []

                    for tool_event in (
                        tool_calling.stream_tool_calls(
                            current_response
                        )
                    ):

                        # -------------------------------------
                        # TOOL START / DONE / ERROR
                        # -------------------------------------

                        if tool_event["type"] in {
                            "tool_start",
                            "tool_done",
                            "tool_error",
                        }:

                            yield AIStreamEvent(
                                type=tool_event["type"],
                                tool_call_id=(
                                    tool_event.get(
                                        "tool_call_id"
                                    )
                                ),
                                tool_name=(
                                    tool_event.get(
                                        "tool_name"
                                    )
                                ),
                                duration_ms=(
                                    tool_event.get(
                                        "duration_ms"
                                    )
                                ),
                                error=(
                                    tool_event.get(
                                        "error"
                                    )
                                ),
                            )

                            continue

                        # -------------------------------------
                        # TOOL RESULT
                        # -------------------------------------

                        if tool_event["type"] == "tool_result":

                            tool_result = (
                                tool_event["result"]
                            )

                            tool_results.append(
                                tool_result
                            )

                            continue

                        raise RuntimeError(
                            "Unknown streaming tool event: "
                            f"{tool_event['type']}"
                        )

                    # -----------------------------------------
                    # VALIDATE EXECUTION
                    # -----------------------------------------

                    if not tool_results:

                        raise RuntimeError(
                            "Tool calls were present but no "
                            "tool results were produced."
                        )

                    # -----------------------------------------
                    # PROVIDER-FACING RESULTS
                    # -----------------------------------------

                    serialized_results = []

                    for tool_result in tool_results:

                        bounded_result = (
                            tool_calling._bound_tool_result(
                                tool_result.result
                            )
                        )

                        serialized_results.append(
                            {
                                "tool_call_id": (
                                    tool_result.tool_call_id
                                ),
                                "name": tool_result.name,
                                "result": bounded_result,
                            }
                        )

                    # -----------------------------------------
                    # SAME PROVIDER WITH TOOL RESULTS
                    # -----------------------------------------

                    # Last round: remove tools so the provider
                    # must write a final answer from the results
                    # it already has instead of asking for more.
                    if iteration == (
                        tool_calling.MAX_TOOL_ITERATIONS - 1
                    ):
                        print(
                            "⚠️ Final round: tools disabled, "
                            "forcing a final answer."
                        )
                        request.tools = []

                    provider_events = self._guard_unexposed_tool_errors(
                        self._stream_provider_with_tool_results(
                            request=request,
                            original_response=current_response,
                            tool_results=serialized_results,
                        )
                    )

                    break

                # ---------------------------------------------
                # UNKNOWN PROVIDER EVENT
                # ---------------------------------------------

                yield event

            # =================================================
            # NO TOOL CALL → PROVIDER FINISHED
            # =================================================

            if not tool_call_detected:

                return

        # ====================================================
        # MAXIMUM ITERATIONS REACHED
        # ====================================================

        raise RuntimeError(
            "Maximum streaming tool-calling iterations "
            f"reached ({tool_calling.MAX_TOOL_ITERATIONS}). "
            "The provider continued requesting tools "
            "without producing a final answer."
        )

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

    async def generate_with_tools(
        self,
        request: AIRequest,
        context: ToolContext,
    ) -> AIResponse:
        """
        Sprint 11 tool-calling entry point.

        Each request receives its own ToolRegistry.
        """

        # ====================================================
        # STEP 1: BUILD REQUEST-SCOPED REGISTRY
        # ====================================================

        registry = await self.tool_router.build_registry(
            context
        )

        # ====================================================
        # STEP 2: ATTACH TOOL DEFINITIONS
        # ====================================================

        request.tools = registry.definitions_for_prompt(request.prompt)

        if not request.tools:

            raise ValueError(
                "No tools are registered for this request."
            )

        # ====================================================
        # STEP 3: CREATE TOOL CALLING SERVICE
        # ====================================================

        tool_calling = ToolCallingService(
            registry=registry,
            provider=self.provider,
            context=context,
            mcp_permission_service=mcp_permission_service,
        )

        try:

            # =================================================
            # STEP 4: INITIAL PROVIDER REQUEST
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
            # STEP 5: PROVIDER ANSWERED DIRECTLY
            # =================================================

            if not initial_response.tool_calls:

                return initial_response

            # =================================================
            # STEP 6: TOOL CALL DETECTED
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
            # STEP 7: COMPLETE TOOL-CALLING LOOP
            # =================================================

            final_response = (
                tool_calling.complete_with_tool_results(
                    request=request,
                    initial_response=initial_response,
                )
            )

            usage_metrics.record(
                final_response
            )

            # =================================================
            # STEP 8: VALIDATE FINAL RESPONSE
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
