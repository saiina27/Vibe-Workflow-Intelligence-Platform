import time
from typing import Any

from app.ai.providers.base import AIProvider
from app.ai.tools.context import ToolContext
from app.ai.tools.executor import ToolExecutor
from app.ai.tools.registry import ToolRegistry
from app.repositories.tool_call_log_repository import (
    ToolCallLogRepository,
)
from app.schemas.ai import AIRequest, AIResponse, ToolResult
from app.mcp.permissions import MCPPermissionService


class ToolCallingService:
    """
    Orchestrates the Vibe tool-calling lifecycle.

    Flow:

        AI Provider
            ↓
        Tool Call
            ↓
        Tool Executor
            ↓
        Tool Result
            ↓
        Tool Call Log
            ↓
        SAME AI Provider
            ↓
        Tool Call again?
            ↓
        YES → execute again
        NO  → final answer

    A maximum number of tool-calling iterations is enforced
    to prevent infinite tool-calling loops.
    """

    # ========================================================
    # SAFETY LIMITS
    # ========================================================

    MAX_TOOL_RESULT_CHARS = 3000

    # Maximum number of provider → tool execution rounds.
    MAX_TOOL_ITERATIONS = 5

    def __init__(
        self,
        registry: ToolRegistry,
        provider: AIProvider,
        context: ToolContext,
        mcp_permission_service: MCPPermissionService,
    ):
        self.registry = registry

        self.executor = ToolExecutor(
            registry,
            context,
            mcp_permission_service=mcp_permission_service,
        )

        self.provider = provider
        self.context = context

        # Repository responsible for tool-call persistence.
        self.tool_call_log_repository = ToolCallLogRepository()

    # ========================================================
    # TOOL RESULT LOGGING
    # ========================================================

    def _save_tool_call_log(
        self,
        tool_call_id: str,
        tool_name: str,
        arguments: dict,
        result: Any,
        status: str,
        error: str | None,
        duration_ms: float,
    ) -> None:
        """
        Persist one tool execution through the repository.

        Logging failures must NEVER break the AI
        tool-calling lifecycle.
        """

        try:
            self.tool_call_log_repository.create(
                self.context.db,
                user_id=self.context.user_id,
                workspace_id=self.context.workspace_id,
                tool_call_id=tool_call_id,
                tool_name=tool_name,
                arguments=arguments or {},
                result=result,
                status=status,
                error=error,
                duration_ms=duration_ms,
            )

        except Exception:
            # Observability must never break tool execution.
            self.context.db.rollback()

    # ========================================================
    # EXECUTE TOOL CALLS
    # ========================================================

    def execute_tool_calls(
        self,
        response: AIResponse,
    ) -> list[ToolResult]:
        """
        Execute every tool requested by the AI provider.

        Each tool call is isolated.

        Successful and failed executions are both logged.

        The provider controls only tool arguments.

        ToolContext remains application-controlled inside
        the registered tool instances.
        """

        if not response.tool_calls:
            return []

        results: list[ToolResult] = []

        for tool_call in response.tool_calls:

            if not tool_call.id:
                raise ValueError(
                    "Tool call ID cannot be empty."
                )

            if not tool_call.name:
                raise ValueError(
                    "Tool call name cannot be empty."
                )

            start_time = time.perf_counter()

            try:
                # ------------------------------------------------
                # EXECUTE TOOL
                # ------------------------------------------------

                result = self.executor.execute(
                    tool_name=tool_call.name,
                    arguments=tool_call.arguments,
                )

                duration_ms = (
                    time.perf_counter() - start_time
                ) * 1000

                tool_result = {
                    "success": True,
                    "data": result,
                }

                results.append(
                    ToolResult(
                        tool_call_id=tool_call.id,
                        name=tool_call.name,
                        result=tool_result,
                    )
                )

                # ------------------------------------------------
                # LOG SUCCESS
                # ------------------------------------------------

                self._save_tool_call_log(
                    tool_call_id=tool_call.id,
                    tool_name=tool_call.name,
                    arguments=tool_call.arguments or {},
                    result=tool_result,
                    status="success",
                    error=None,
                    duration_ms=duration_ms,
                )

            except Exception as exc:

                duration_ms = (
                    time.perf_counter() - start_time
                ) * 1000

                error_message = str(exc)

                tool_result = {
                    "success": False,
                    "error": error_message,
                }

                # ------------------------------------------------
                # RETURN ERROR AS TOOL RESULT
                # ------------------------------------------------

                results.append(
                    ToolResult(
                        tool_call_id=tool_call.id,
                        name=tool_call.name,
                        result=tool_result,
                    )
                )

                # ------------------------------------------------
                # LOG FAILURE
                # ------------------------------------------------

                self._save_tool_call_log(
                    tool_call_id=tool_call.id,
                    tool_name=tool_call.name,
                    arguments=tool_call.arguments or {},
                    result=tool_result,
                    status="failed",
                    error=error_message,
                    duration_ms=duration_ms,
                )

        return results

    # ========================================================
    # BOUND TOOL RESULT
    # ========================================================

    @classmethod
    def _bound_tool_result(
        cls,
        result: Any,
    ) -> Any:
        """
        Keep provider-facing tool results bounded.

        Tool execution itself is never truncated.
        Database logging keeps the original result.
        Only the result sent back to the provider is bounded.
        """

        max_chars = cls.MAX_TOOL_RESULT_CHARS

        # ----------------------------------------------------
        # DICTIONARY RESULT
        # ----------------------------------------------------

        if isinstance(result, dict):

            bounded = dict(result)

            # -----------------------------------------------
            # SUCCESS DATA
            # -----------------------------------------------

            if "data" in bounded:

                data = bounded["data"]

                # -------------------------------------------
                # LIST DATA
                # -------------------------------------------

                if isinstance(data, list):

                    bounded_items = []
                    total_chars = 0

                    for item in data:

                        item_text = str(item)

                        remaining = (
                            max_chars - total_chars
                        )

                        if remaining <= 0:
                            break

                        bounded_item = (
                            item_text[:remaining]
                        )

                        bounded_items.append(
                            bounded_item
                        )

                        total_chars += len(
                            bounded_item
                        )

                    bounded["data"] = bounded_items

                # -------------------------------------------
                # STRING DATA
                # -------------------------------------------

                elif isinstance(data, str):

                    bounded["data"] = data[:max_chars]

                # -------------------------------------------
                # OTHER DATA TYPES
                # -------------------------------------------

                else:

                    data_text = str(data)

                    bounded["data"] = (
                        data_text[:max_chars]
                    )

            # -----------------------------------------------
            # ERROR
            # -----------------------------------------------

            if "error" in bounded:

                bounded["error"] = str(
                    bounded["error"]
                )[:max_chars]

            return bounded

        # ----------------------------------------------------
        # NON-DICT RESULT
        # ----------------------------------------------------

        return str(result)[:max_chars]

    # ========================================================
    # COMPLETE TOOL-CALLING LOOP
    # ========================================================

    def complete_with_tool_results(
        self,
        request: AIRequest,
        initial_response: AIResponse,
    ) -> AIResponse:
        """
        Complete the provider tool-calling lifecycle.

        Supports bounded multi-tool execution.

        Flow:

            Initial AI response
                ↓
            Tool calls
                ↓
            Execute tools
                ↓
            Tool results
                ↓
            SAME provider
                ↓
            Tool calls again?
                ↓
            YES → repeat
            NO  → final answer

        Maximum:
            MAX_TOOL_ITERATIONS = 5
        """

        # ====================================================
        # INITIAL VALIDATION
        # ====================================================

        if not initial_response.tool_calls:
            raise ValueError(
                "Cannot complete tool calling because "
                "the initial response contains no tool calls."
            )

        current_response = initial_response

        # ====================================================
        # MULTI-TOOL LOOP
        # ====================================================

        for iteration in range(
            1,
            self.MAX_TOOL_ITERATIONS + 1,
        ):

            print("=" * 60)

            print("AI TOOL-CALLING ITERATION")

            print(
                f"Iteration: "
                f"{iteration}/"
                f"{self.MAX_TOOL_ITERATIONS}"
            )

            print(
                f"Tool calls: "
                f"{len(current_response.tool_calls)}"
            )

            print(
                f"Provider: "
                f"{current_response.provider}"
            )

            print("=" * 60)

            # =================================================
            # STEP 1: EXECUTE CURRENT TOOL CALLS
            # =================================================

            tool_results = self.execute_tool_calls(
                current_response
            )

            if not tool_results:
                raise RuntimeError(
                    "Tool calls were present but no "
                    "tool results were produced."
                )

            # =================================================
            # STEP 2: BOUND PROVIDER-FACING RESULTS
            # =================================================

            serialized_results = []

            for result in tool_results:

                bounded_result = (
                    self._bound_tool_result(
                        result.result
                    )
                )

                serialized_results.append(
                    {
                        "tool_call_id": (
                            result.tool_call_id
                        ),
                        "name": result.name,
                        "result": bounded_result,
                    }
                )

            # =================================================
            # STEP 3: SEND RESULTS TO SAME PROVIDER
            # =================================================

            next_response = (
                self.provider.generate_with_tool_results(
                    request=request,
                    original_response=current_response,
                    tool_results=serialized_results,
                )
            )

            # =================================================
            # STEP 4: VALIDATE PROVIDER RESPONSE
            # =================================================

            if next_response is None:
                raise RuntimeError(
                    "Provider returned no response "
                    "after tool execution."
                )

            # =================================================
            # STEP 5: PROVIDER REQUESTED MORE TOOLS
            # =================================================

            if next_response.tool_calls:

                print(
                    "🔧 Provider requested another "
                    "tool-calling iteration."
                )

                current_response = next_response

                continue

            # =================================================
            # STEP 6: FINAL ANSWER
            # =================================================

            if next_response.content is None:
                raise RuntimeError(
                    "Provider returned no final content "
                    "after tool execution."
                )

            print("=" * 60)

            print("✅ TOOL-CALLING LOOP COMPLETED")

            print(
                f"Iterations used: {iteration}"
            )

            print("=" * 60)

            return next_response

        # ====================================================
        # MAX ITERATIONS REACHED
        # ====================================================

        raise RuntimeError(
            "Maximum tool-calling iterations reached "
            f"({self.MAX_TOOL_ITERATIONS}). "
            "The provider continued requesting tools "
            "without producing a final answer."
        )