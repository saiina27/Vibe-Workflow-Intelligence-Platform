import json
import time
from collections.abc import Iterator
from typing import Any

from groq import Groq

from app.ai.providers.base import AIProvider
from app.core.config import settings
from app.schemas.ai import (
    AIRequest,
    AIResponse,
    AIStreamEvent,
    ToolCall,
)


class GroqProvider(AIProvider):

    def __init__(self):

        self.client = Groq(
            api_key=settings.groq_api_key
        )

        self.model = settings.groq_model

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

        choice = response.choices[0]

        content = (
            choice.message.content
            or ""
        )

        usage = response.usage

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
            provider_response=response,
        )

    # ========================================================
    # NORMAL STREAMING
    # ========================================================

    def stream(
        self,
        request: AIRequest,
    ) -> Iterator[str]:

        model = (
            request.model
            or self.model
        )

        response_stream = (
            self.client.chat.completions.create(
                model=model,
                messages=[
                    {
                        "role": "user",
                        "content": request.prompt,
                    }
                ],
                temperature=request.temperature,
                max_tokens=request.max_tokens,
                stream=True,
            )
        )

        for chunk in response_stream:

            if not chunk.choices:
                continue

            delta = chunk.choices[0].delta

            if delta.content:
                yield delta.content

    # ========================================================
    # TOOL DEFINITIONS
    # ========================================================

    @staticmethod
    def _build_tools(
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
    # TOOL CALL PARSER
    # ========================================================

    @staticmethod
    def _parse_tool_calls(
        message: Any,
    ) -> list[ToolCall]:

        tool_calls: list[ToolCall] = []

        for tool_call in (
            message.tool_calls
            or []
        ):

            function = tool_call.function

            raw_arguments = (
                function.arguments
                or "{}"
            )

            try:

                arguments = json.loads(
                    raw_arguments
                )

            except (
                json.JSONDecodeError,
                TypeError,
            ) as exc:

                raise ValueError(
                    f"Invalid arguments returned "
                    f"for Groq tool "
                    f"'{function.name}'."
                ) from exc

            if not isinstance(
                arguments,
                dict,
            ):

                raise ValueError(
                    f"Groq tool arguments for "
                    f"'{function.name}' must be "
                    "a JSON object."
                )

            tool_calls.append(
                ToolCall(
                    id=tool_call.id,
                    name=function.name,
                    arguments=arguments,
                )
            )

        return tool_calls

    # ========================================================
    # ASSISTANT TOOL MESSAGE
    # ========================================================

    @staticmethod
    def _build_assistant_tool_message(
        message: Any,
    ) -> dict[str, Any]:

        tool_calls = []

        for tool_call in (
            message.tool_calls
            or []
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
                            or "{}"
                        ),
                    },
                }
            )

        return {
            "role": "assistant",
            "content": (
                message.content
                or ""
            ),
            "tool_calls": tool_calls,
        }

    # ========================================================
    # INITIAL TOOL-CALLING GENERATION
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
                "Groq tool configuration requires "
                "at least one tool."
            )

        user_message = {
            "role": "user",
            "content": request.prompt,
        }

        response = (
            self.client.chat.completions.create(
                model=model,
                messages=[
                    user_message
                ],
                tools=tools,
                tool_choice="auto",
                temperature=request.temperature,
                max_tokens=request.max_tokens,
            )
        )

        latency = (
            time.time() - start_time
        ) * 1000

        message = response.choices[0].message

        tool_calls = (
            self._parse_tool_calls(
                message
            )
        )

        content = (
            message.content
            or ""
        )

        provider_context: list[Any] = [
            user_message
        ]

        if tool_calls:

            provider_context.append(
                self._build_assistant_tool_message(
                    message
                )
            )

        usage = response.usage

        return AIResponse(
            content=(
                None
                if tool_calls
                else content
            ),
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
    # STREAMING TOOL-CALLING GENERATION
    # ========================================================

    def stream_with_tools(
        self,
        request: AIRequest,
    ) -> Iterator[AIStreamEvent]:
        """
        Stream a Groq response with native tool calling.

        Normal text is emitted incrementally.

        Tool-call deltas are accumulated because Groq may
        split tool-call IDs, names, and JSON arguments across
        multiple stream chunks.

        Once the provider finishes the response, complete
        ToolCall objects are emitted through a provider-
        independent AIStreamEvent.
        """

        model = (
            request.model
            or self.model
        )

        tools = self._build_tools(
            request
        )

        if not tools:

            raise ValueError(
                "Groq streaming tool configuration "
                "requires at least one tool."
            )

        user_message = {
            "role": "user",
            "content": request.prompt,
        }

        response_stream = (
            self.client.chat.completions.create(
                model=model,
                messages=[
                    user_message
                ],
                tools=tools,
                tool_choice="auto",
                temperature=request.temperature,
                max_tokens=request.max_tokens,
                stream=True,
            )
        )

        tool_call_state: dict[
            int,
            dict[str, Any],
        ] = {}

        assistant_content: list[str] = []

        for chunk in response_stream:

            if not chunk.choices:
                continue

            delta = chunk.choices[0].delta

            # ------------------------------------------------
            # Normal streamed text
            # ------------------------------------------------

            if delta.content:

                assistant_content.append(
                    delta.content
                )

                yield AIStreamEvent(
                    type="content",
                    text=delta.content,
                    model=model,
                    provider="groq",
                )

            # ------------------------------------------------
            # Native tool-call deltas
            # ------------------------------------------------

            for tool_delta in (
                delta.tool_calls
                or []
            ):

                index = (
                    tool_delta.index
                )

                state = tool_call_state.setdefault(
                    index,
                    {
                        "id": "",
                        "name": "",
                        "arguments": "",
                    },
                )

                if tool_delta.id:

                    state["id"] += (
                        tool_delta.id
                    )

                function = (
                    tool_delta.function
                )

                if function:

                    if function.name:

                        state["name"] += (
                            function.name
                        )

                    if function.arguments:

                        state["arguments"] += (
                            function.arguments
                        )

        # ----------------------------------------------------
        # Convert accumulated native tool calls into our
        # provider-independent ToolCall objects.
        # ----------------------------------------------------

        tool_calls: list[ToolCall] = []

        for index in sorted(
            tool_call_state
        ):

            state = tool_call_state[index]

            tool_call_id = (
                state["id"]
                or f"call_{index + 1}"
            )

            name = state["name"]

            if not name:

                raise ValueError(
                    "Groq returned a tool call "
                    "without a function name."
                )

            raw_arguments = (
                state["arguments"]
                or "{}"
            )

            try:

                arguments = json.loads(
                    raw_arguments
                )

            except (
                json.JSONDecodeError,
                TypeError,
            ) as exc:

                raise ValueError(
                    f"Invalid streamed arguments "
                    f"returned for Groq tool "
                    f"'{name}'."
                ) from exc

            if not isinstance(
                arguments,
                dict,
            ):

                raise ValueError(
                    f"Groq streamed arguments "
                    f"for '{name}' must be "
                    "a JSON object."
                )

            tool_calls.append(
                ToolCall(
                    id=tool_call_id,
                    name=name,
                    arguments=arguments,
                )
            )

        # ----------------------------------------------------
        # Preserve the exact native assistant tool-call
        # message for the subsequent Groq roundtrip.
        # ----------------------------------------------------

        provider_context: list[Any] = [
            user_message
        ]

        if tool_calls:

            native_tool_calls = []

            for tool_call in tool_calls:

                native_tool_calls.append(
                    {
                        "id": tool_call.id,
                        "type": "function",
                        "function": {
                            "name": tool_call.name,
                            "arguments": json.dumps(
                                tool_call.arguments
                            ),
                        },
                    }
                )

            provider_context.append(
                {
                    "role": "assistant",
                    "content": (
                        "".join(
                            assistant_content
                        )
                        or None
                    ),
                    "tool_calls": native_tool_calls,
                }
            )

            yield AIStreamEvent(
                type="tool_call",
                tool_calls=tool_calls,
                model=model,
                provider="groq",
                provider_context=provider_context,
            )

    # ========================================================
    # TOOL RESULTS → NEXT GROQ RESPONSE
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

        if not tool_results:

            raise ValueError(
                "Groq tool-result roundtrip requires "
                "at least one tool result."
            )

        if not original_response.tool_calls:

            raise ValueError(
                "Original Groq response contains "
                "no tool calls."
            )

        previous_context = (
            original_response.provider_context
        )

        if not previous_context:

            raise ValueError(
                "Groq provider conversation context "
                "is missing."
            )

        messages: list[Any] = list(
            previous_context
        )

        expected_tool_call_ids = {
            tool_call.id
            for tool_call in (
                original_response.tool_calls
            )
            if tool_call.id
        }

        seen_tool_call_ids: set[str] = set()

        for tool_result in tool_results:

            tool_call_id = tool_result.get(
                "tool_call_id"
            )

            name = tool_result.get(
                "name"
            )

            result = tool_result.get(
                "result"
            )

            if not tool_call_id:

                raise ValueError(
                    "Tool result is missing "
                    "'tool_call_id'."
                )

            if not name:

                raise ValueError(
                    "Tool result is missing "
                    "'name'."
                )

            if "result" not in tool_result:

                raise ValueError(
                    f"Tool result for '{name}' "
                    "is missing 'result'."
                )

            if tool_call_id in seen_tool_call_ids:

                raise ValueError(
                    f"Duplicate tool result for "
                    f"tool call '{tool_call_id}'."
                )

            if tool_call_id not in expected_tool_call_ids:

                raise ValueError(
                    f"Tool result references unknown "
                    f"Groq tool call ID "
                    f"'{tool_call_id}'."
                )

            seen_tool_call_ids.add(
                tool_call_id
            )

            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call_id,
                    "content": (
                        result
                        if isinstance(
                            result,
                            str,
                        )
                        else json.dumps(
                            result
                        )
                    ),
                }
            )

        missing_tool_call_ids = (
            expected_tool_call_ids
            - seen_tool_call_ids
        )

        if missing_tool_call_ids:

            raise ValueError(
                "Missing Groq tool results for "
                f"tool call IDs: "
                f"{sorted(missing_tool_call_ids)}"
            )

        tools = self._build_tools(
            request
        )

        response = (
            self.client.chat.completions.create(
                model=model,
                messages=messages,
                tools=tools,
                tool_choice="auto",
                temperature=request.temperature,
                max_tokens=request.max_tokens,
            )
        )

        latency = (
            time.time() - start_time
        ) * 1000

        message = response.choices[0].message

        tool_calls = (
            self._parse_tool_calls(
                message
            )
        )

        content = (
            message.content
            or ""
        )

        updated_context = list(
            messages
        )

        if tool_calls:

            updated_context.append(
                self._build_assistant_tool_message(
                    message
                )
            )

        usage = response.usage

        return AIResponse(
            content=(
                None
                if tool_calls
                else content
            ),
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

    # ========================================================
    # STREAMING TOOL RESULTS → NEXT GROQ RESPONSE
    # ========================================================

    def stream_with_tool_results(
        self,
        request: AIRequest,
        original_response: AIResponse,
        tool_results: list[dict[str, Any]],
    ) -> Iterator[AIStreamEvent]:
        """
        Stream Groq's response after real tool execution.
        """

        model = (
            request.model
            or self.model
        )

        if not tool_results:

            raise ValueError(
                "Groq streaming tool-result roundtrip "
                "requires at least one tool result."
            )

        if not original_response.tool_calls:

            raise ValueError(
                "Original Groq response contains "
                "no tool calls."
            )

        previous_context = (
            original_response.provider_context
        )

        if not previous_context:

            raise ValueError(
                "Groq provider conversation context "
                "is missing."
            )

        messages: list[Any] = list(
            previous_context
        )

        expected_tool_call_ids = {
            tool_call.id
            for tool_call in (
                original_response.tool_calls
            )
            if tool_call.id
        }

        seen_tool_call_ids: set[str] = set()

        for tool_result in tool_results:

            tool_call_id = tool_result.get(
                "tool_call_id"
            )

            name = tool_result.get(
                "name"
            )

            result = tool_result.get(
                "result"
            )

            if not tool_call_id:

                raise ValueError(
                    "Tool result is missing "
                    "'tool_call_id'."
                )

            if not name:

                raise ValueError(
                    "Tool result is missing "
                    "'name'."
                )

            if "result" not in tool_result:

                raise ValueError(
                    f"Tool result for '{name}' "
                    "is missing 'result'."
                )

            if tool_call_id in seen_tool_call_ids:

                raise ValueError(
                    f"Duplicate tool result for "
                    f"tool call '{tool_call_id}'."
                )

            if tool_call_id not in expected_tool_call_ids:

                raise ValueError(
                    f"Tool result references unknown "
                    f"Groq tool call ID "
                    f"'{tool_call_id}'."
                )

            seen_tool_call_ids.add(
                tool_call_id
            )

            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call_id,
                    "content": (
                        result
                        if isinstance(
                            result,
                            str,
                        )
                        else json.dumps(
                            result
                        )
                    ),
                }
            )

        missing_tool_call_ids = (
            expected_tool_call_ids
            - seen_tool_call_ids
        )

        if missing_tool_call_ids:

            raise ValueError(
                "Missing Groq tool results for "
                f"tool call IDs: "
                f"{sorted(missing_tool_call_ids)}"
            )

        tools = self._build_tools(
            request
        )

        response_stream = (
            self.client.chat.completions.create(
                model=model,
                messages=messages,
                tools=tools,
                tool_choice="auto",
                temperature=request.temperature,
                max_tokens=request.max_tokens,
                stream=True,
            )
        )

        tool_call_state: dict[
            int,
            dict[str, Any],
        ] = {}

        assistant_content: list[str] = []

        for chunk in response_stream:

            if not chunk.choices:
                continue

            delta = chunk.choices[0].delta

            if delta.content:

                assistant_content.append(
                    delta.content
                )

                yield AIStreamEvent(
                    type="content",
                    text=delta.content,
                    model=model,
                    provider="groq",
                )

            for tool_delta in (
                delta.tool_calls
                or []
            ):

                index = (
                    tool_delta.index
                )

                state = tool_call_state.setdefault(
                    index,
                    {
                        "id": "",
                        "name": "",
                        "arguments": "",
                    },
                )

                if tool_delta.id:

                    state["id"] += (
                        tool_delta.id
                    )

                function = (
                    tool_delta.function
                )

                if function:

                    if function.name:

                        state["name"] += (
                            function.name
                        )

                    if function.arguments:

                        state["arguments"] += (
                            function.arguments
                        )

        tool_calls: list[ToolCall] = []

        for index in sorted(
            tool_call_state
        ):

            state = tool_call_state[index]

            tool_call_id = (
                state["id"]
                or f"call_{index + 1}"
            )

            name = state["name"]

            if not name:

                raise ValueError(
                    "Groq returned a streamed tool call "
                    "without a function name."
                )

            raw_arguments = (
                state["arguments"]
                or "{}"
            )

            try:

                arguments = json.loads(
                    raw_arguments
                )

            except (
                json.JSONDecodeError,
                TypeError,
            ) as exc:

                raise ValueError(
                    f"Invalid streamed arguments "
                    f"returned for Groq tool "
                    f"'{name}'."
                ) from exc

            if not isinstance(
                arguments,
                dict,
            ):

                raise ValueError(
                    f"Groq streamed arguments "
                    f"for '{name}' must be "
                    "a JSON object."
                )

            tool_calls.append(
                ToolCall(
                    id=tool_call_id,
                    name=name,
                    arguments=arguments,
                )
            )

        if tool_calls:

            updated_context = list(
                messages
            )

            native_tool_calls = []

            for tool_call in tool_calls:

                native_tool_calls.append(
                    {
                        "id": tool_call.id,
                        "type": "function",
                        "function": {
                            "name": tool_call.name,
                            "arguments": json.dumps(
                                tool_call.arguments
                            ),
                        },
                    }
                )

            updated_context.append(
                {
                    "role": "assistant",
                    "content": (
                        "".join(
                            assistant_content
                        )
                        or None
                    ),
                    "tool_calls": native_tool_calls,
                }
            )

            yield AIStreamEvent(
                type="tool_call",
                tool_calls=tool_calls,
                model=model,
                provider="groq",
                provider_context=updated_context,
            )
