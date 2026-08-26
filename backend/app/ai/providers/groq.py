import json
import time
from typing import Any

from groq import Groq

from app.ai.providers.base import AIProvider
from app.core.config import settings
from app.schemas.ai import AIRequest, AIResponse, ToolCall


class GroqProvider(AIProvider):

    def __init__(self):

        self.client = Groq(
            api_key=settings.groq_api_key
        )

        self.model = (
            settings.groq_model
            or "llama-3.3-70b-versatile"
        )

    # ========================================================
    # NORMAL GENERATION
    # ========================================================

    def generate(
        self,
        request: AIRequest,
    ) -> AIResponse:

        start_time = time.time()

        model = (
            request.model
            or self.model
        )

        response = self.client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "user",
                    "content": request.prompt,
                }
            ],
            temperature=request.temperature,
            max_tokens=request.max_tokens,
        )

        latency = (
            time.time() - start_time
        ) * 1000

        message = response.choices[0].message
        usage = response.usage

        return AIResponse(
            content=message.content,
            model=model,
            provider="groq",
            input_tokens=(
                usage.prompt_tokens
                if usage
                else 0
            ),
            output_tokens=(
                usage.completion_tokens
                if usage
                else 0
            ),
            latency_ms=latency,
            provider_response=response,
        )

    # ========================================================
    # BUILD NATIVE GROQ TOOLS
    # ========================================================

    def _build_tools(
        self,
        request: AIRequest,
    ) -> list[dict[str, Any]]:

        return [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters,
                },
            }
            for tool in request.tools
        ]

    # ========================================================
    # PARSE GROQ TOOL CALLS
    # ========================================================

    def _parse_tool_calls(
        self,
        message: Any,
    ) -> list[ToolCall]:

        tool_calls: list[ToolCall] = []

        if not message.tool_calls:
            return tool_calls

        for index, tool_call in enumerate(
            message.tool_calls
        ):

            function = tool_call.function

            if not function.name:

                raise ValueError(
                    "Groq returned a tool call "
                    "without a function name."
                )

            arguments: dict[str, Any] = {}

            if function.arguments:

                try:

                    parsed_arguments = json.loads(
                        function.arguments
                    )

                    if not isinstance(
                        parsed_arguments,
                        dict,
                    ):

                        raise ValueError(
                            f"Tool arguments for "
                            f"'{function.name}' must "
                            f"be a JSON object."
                        )

                    arguments = parsed_arguments

                except json.JSONDecodeError as exc:

                    raise ValueError(
                        f"Invalid JSON arguments "
                        f"for tool '{function.name}': "
                        f"{exc}"
                    ) from exc

            tool_call_id = (
                tool_call.id
                or f"call_{index + 1}"
            )

            tool_calls.append(
                ToolCall(
                    id=tool_call_id,
                    name=function.name,
                    arguments=arguments,
                )
            )

        return tool_calls

    # ========================================================
    # BUILD ASSISTANT TOOL-CALL MESSAGE
    # ========================================================

    def _build_assistant_tool_message(
        self,
        message: Any,
    ) -> dict[str, Any]:

        tool_calls = []

        for tool_call in (
            message.tool_calls or []
        ):

            tool_calls.append(
                {
                    "id": tool_call.id,
                    "type": "function",
                    "function": {
                        "name": (
                            tool_call.function.name
                        ),
                        "arguments": (
                            tool_call.function.arguments
                        ),
                    },
                }
            )

        return {
            "role": "assistant",
            "content": message.content,
            "tool_calls": tool_calls,
        }

    # ========================================================
    # TOOL-CALLING GENERATION
    # ========================================================

    def generate_with_tools(
        self,
        request: AIRequest,
    ) -> AIResponse:

        start_time = time.time()

        model = (
            request.model
            or self.model
        )

        tools = self._build_tools(
            request
        )

        if not tools:

            raise ValueError(
                "Tool-enabled generation requires "
                "at least one tool."
            )

        # ====================================================
        # INITIAL CONVERSATION
        # ====================================================

        messages: list[dict[str, Any]] = [
            {
                "role": "user",
                "content": request.prompt,
            }
        ]

        response = self.client.chat.completions.create(
            model=model,
            messages=messages,
            tools=tools,
            tool_choice="auto",
            temperature=request.temperature,
            max_tokens=request.max_tokens,
        )

        latency = (
            time.time() - start_time
        ) * 1000

        message = response.choices[0].message
        usage = response.usage

        # ====================================================
        # PARSE TOOL CALLS
        # ====================================================

        tool_calls = self._parse_tool_calls(
            message
        )

        # ====================================================
        # PRESERVE PROVIDER CONVERSATION
        # ====================================================

        provider_context = list(
            messages
        )

        if tool_calls:

            provider_context.append(
                self._build_assistant_tool_message(
                    message
                )
            )

        # ====================================================
        # DIRECT ANSWER
        # ====================================================

        content = None

        if not tool_calls:

            content = message.content

        return AIResponse(
            content=content,
            model=model,
            provider="groq",
            input_tokens=(
                usage.prompt_tokens
                if usage
                else 0
            ),
            output_tokens=(
                usage.completion_tokens
                if usage
                else 0
            ),
            latency_ms=latency,
            tool_calls=tool_calls,
            provider_response=response,
            provider_context=provider_context,
        )

    # ========================================================
    # TOOL RESULT ROUND-TRIP
    # ========================================================

    def generate_with_tool_results(
        self,
        request: AIRequest,
        original_response: AIResponse,
        tool_results: list[dict[str, Any]],
    ) -> AIResponse:

        start_time = time.time()

        model = (
            request.model
            or self.model
        )

        # ====================================================
        # VALIDATE ORIGINAL PROVIDER RESPONSE
        # ====================================================

        provider_response = (
            original_response.provider_response
        )

        if provider_response is None:

            raise ValueError(
                "Original provider response is required "
                "for Groq tool-result round-trip."
            )

        if not original_response.tool_calls:

            raise ValueError(
                "Original response contains no tool calls."
            )

        original_message = (
            provider_response
            .choices[0]
            .message
        )

        original_provider_tool_calls = (
            original_message.tool_calls
            or []
        )

        if not original_provider_tool_calls:

            raise ValueError(
                "Original Groq response contains no "
                "native tool calls."
            )

        # ====================================================
        # BUILD ORIGINAL TOOL CALL ID SET
        # ====================================================

        original_tool_call_ids = {
            tool_call.id
            for tool_call in (
                original_provider_tool_calls
            )
            if tool_call.id
        }

        if not original_tool_call_ids:

            raise ValueError(
                "Original Groq tool calls contain no "
                "valid tool call IDs."
            )

        # ====================================================
        # VALIDATE TOOL RESULTS
        # ====================================================

        if not tool_results:

            raise ValueError(
                "Tool results are required for "
                "Groq tool-result round-trip."
            )

        result_ids: set[str] = set()

        for tool_result in tool_results:

            tool_call_id = tool_result.get(
                "tool_call_id"
            )

            if not tool_call_id:

                raise ValueError(
                    "Tool result is missing "
                    "'tool_call_id'."
                )

            if tool_call_id in result_ids:

                raise ValueError(
                    f"Duplicate tool result for "
                    f"tool call '{tool_call_id}'."
                )

            if tool_call_id not in (
                original_tool_call_ids
            ):

                raise ValueError(
                    f"Tool result references unknown "
                    f"tool call ID '{tool_call_id}'."
                )

            if "result" not in tool_result:

                raise ValueError(
                    "Tool result is missing "
                    "'result'."
                )

            result_ids.add(
                tool_call_id
            )

        # ====================================================
        # CHECK FOR MISSING RESULTS
        # ====================================================

        missing_ids = (
            original_tool_call_ids
            - result_ids
        )

        if missing_ids:

            raise ValueError(
                "Missing tool results for tool call IDs: "
                f"{sorted(missing_ids)}"
            )

        # ====================================================
        # RESTORE COMPLETE CONVERSATION
        # ====================================================

        previous_context = (
            original_response.provider_context
        )

        if not previous_context:

            raise ValueError(
                "Groq provider conversation context "
                "is missing."
            )

        messages: list[dict[str, Any]] = [
            dict(message)
            for message in previous_context
        ]

        # ====================================================
        # APPEND TOOL RESULTS
        # ====================================================

        for tool_result in tool_results:

            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": (
                        tool_result["tool_call_id"]
                    ),
                    "content": str(
                        tool_result["result"]
                    ),
                }
            )

        # ====================================================
        # NEXT GROQ REQUEST
        # ====================================================

        tools = self._build_tools(
            request
        )

        response = self.client.chat.completions.create(
            model=model,
            messages=messages,
            tools=tools,
            tool_choice="auto",
            temperature=request.temperature,
            max_tokens=request.max_tokens,
        )

        latency = (
            time.time() - start_time
        ) * 1000

        message = response.choices[0].message
        usage = response.usage

        # ====================================================
        # PARSE NEXT TOOL CALLS
        # ====================================================

        tool_calls = self._parse_tool_calls(
            message
        )

        # ====================================================
        # UPDATE PROVIDER CONVERSATION STATE
        # ====================================================

        updated_context = list(
            messages
        )

        if tool_calls:

            updated_context.append(
                self._build_assistant_tool_message(
                    message
                )
            )

        # ====================================================
        # FINAL ANSWER VS NEXT TOOL CALL
        # ====================================================

        content = None

        if not tool_calls:

            content = message.content

        return AIResponse(
            content=content,
            model=model,
            provider="groq",
            input_tokens=(
                usage.prompt_tokens
                if usage
                else 0
            ),
            output_tokens=(
                usage.completion_tokens
                if usage
                else 0
            ),
            latency_ms=latency,
            tool_calls=tool_calls,
            provider_response=response,
            provider_context=updated_context,
        )