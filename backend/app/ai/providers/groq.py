import json
import re
import time
from collections.abc import Iterator
from typing import Any

from groq import Groq, RateLimitError

from app.ai.providers import groq_budget as budget
from app.ai.providers.base import AIProvider
from app.core.config import settings
from app.schemas.ai import (
    AIRequest,
    AIResponse,
    AIStreamEvent,
    ToolCall,
)


def _effort_kwargs() -> dict:
    """
    Optional speed-up: GROQ_REASONING_EFFORT=low|medium|high makes
    gpt-oss models think less. Unset means no change.
    """

    import os

    value = (os.getenv("GROQ_REASONING_EFFORT") or "").strip().lower()

    if value not in {"low", "medium", "high"}:
        return {}

    try:
        from app.core.config import settings

        model = str(settings.groq_model or "")
    except Exception:
        return {}

    if "gpt-oss" not in model:
        return {}

    return {"extra_body": {"reasoning_effort": value}}


def _log_http_response(response) -> None:
    """Print Groq's rate-limit headers (diagnostics only, never raises)."""

    try:
        headers = response.headers
        remaining = headers.get("x-ratelimit-remaining-tokens")

        print(
            f"⏱️ Groq HTTP {response.status_code} | remaining tokens "
            f"{remaining} | reset {headers.get('x-ratelimit-reset-tokens')} "
            f"| retry-after {headers.get('retry-after')}"
        )

        model = getattr(budget.CURRENT, "model", None)

        if model and remaining is not None:
            budget.BUDGET.update(
                model,
                int(float(remaining)),
                int(float(
                    headers.get("x-ratelimit-limit-tokens")
                    or budget.DEFAULT_LIMIT
                )),
                budget.parse_duration(headers.get("x-ratelimit-reset-tokens")),
            )
    except Exception:
        pass


def _make_client():
    """Groq client that logs rate-limit headers; plain client as fallback."""

    try:
        from groq import DefaultHttpxClient

        return Groq(
            api_key=settings.groq_api_key,
            http_client=DefaultHttpxClient(
                event_hooks={"response": [_log_http_response]}
            ),
        )
    except Exception:
        return Groq(api_key=settings.groq_api_key)


class GroqProvider(AIProvider):

    def __init__(self):

        self.client = _make_client()

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
            **_effort_kwargs(),
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
                **_effort_kwargs(),
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
    # RATE LIMIT RETRY (per-minute limits only)
    # ========================================================

    @staticmethod
    def _retry_after_seconds(message: str) -> float | None:
        """
        Parse Groq's "Please try again in 1.4s / 112ms / 1m17s".
        """

        match = re.search(
            r"try again in (?:(\d+)m)?([\d.]+)(ms|s)",
            message,
        )

        if not match:
            return None

        minutes = int(match.group(1) or 0)
        value = float(match.group(2))
        seconds = value / 1000 if match.group(3) == "ms" else value

        return minutes * 60 + seconds

    def _create_with_rate_limit_retry(self, **kwargs):
        """
        Picks the Groq model with enough token budget (see
        GROQ_MODEL_POOL), and tries the next one when a model is
        rate limited. Without a pool this is the plain call.
        """

        main = kwargs.get("model")
        models = budget.candidate_models(main, kwargs)

        for index, model in enumerate(models):
            if model is not None:
                kwargs["model"] = model

            budget.CURRENT.model = kwargs.get("model")

            if len(models) > 1:
                print(
                    f"⏱️ Groq model: {model} "
                    f"(candidates: {', '.join(str(m) for m in models)})"
                )

            try:
                return self._create_with_rate_limit_retry_inner(**kwargs)

            except RateLimitError as exc:
                if "per day" in str(exc):
                    budget.BUDGET.block(model)

                if index == len(models) - 1:
                    raise

                print(
                    f"⏱️ Groq {model} is rate limited; trying "
                    f"{models[index + 1]}"
                )

    def _create_with_rate_limit_retry_inner(self, **kwargs):
        """
        chat.completions.create() with a short retry for
        per-minute (TPM) 429s. Per-day (TPD) limits and long
        waits are raised immediately.
        """

        max_retries = 2

        for attempt in range(max_retries + 1):
            try:
                import time as _time

                try:
                    message_tokens = len(
                        json.dumps(kwargs.get("messages", []), default=str)
                    ) // 4
                    tool_tokens = len(
                        json.dumps(kwargs.get("tools") or [], default=str)
                    ) // 4
                    effort = (kwargs.get("extra_body") or {}).get(
                        "reasoning_effort", "default"
                    )

                    print(
                        f"⏱️ Groq request ≈ {message_tokens} message tokens + "
                        f"{tool_tokens} tool-definition tokens "
                        f"(reasoning: {effort})"
                    )
                except Exception:
                    pass

                started = _time.perf_counter()
                response = self.client.chat.completions.create(**kwargs)
                kind = "stream opened" if kwargs.get("stream") else "reply"
                print(
                    f"⏱️ Groq {kind} in "
                    f"{(_time.perf_counter() - started) * 1000:.0f} ms "
                    f"({kwargs.get('model')})"
                )

                return response

            except RateLimitError as exc:
                message = str(exc)
                wait = self._retry_after_seconds(message)

                if (
                    "per minute" not in message
                    or wait is None
                    or wait > 8
                    or attempt == max_retries
                ):
                    raise

                print(
                    f"Groq TPM 429: retrying in {wait + 0.5:.1f}s "
                    f"(attempt {attempt + 1}/{max_retries})"
                )

                time.sleep(wait + 0.5)

    # ========================================================
    # TOOL DEFINITIONS
    # ========================================================

    @staticmethod
    def _build_tools(
        request: AIRequest,
    ) -> list[dict[str, Any]]:

        tools = [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters,
                },
            }
            for tool in (request.tools or [])
        ]

        return tools

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
                **_effort_kwargs(),
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

        response_stream = self._create_with_rate_limit_retry(
            model=model,
            messages=[user_message],
            tools=tools,
            tool_choice="auto",
            temperature=request.temperature,
            max_tokens=request.max_tokens,
            **_effort_kwargs(),
            stream=True,
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
                **_effort_kwargs(),
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

        extra_kwargs: dict[str, Any] = {}

        # No tools left (final round): do not send the
        # tools parameter so the model must answer in text.
        if tools:
            extra_kwargs["tools"] = tools
            extra_kwargs["tool_choice"] = "auto"
        else:
            messages.append(
                {
                    "role": "user",
                    "content": (
                        "You already have all the tool results "
                        "you need. Do not call any tools. Write "
                        "the final answer to my question now, "
                        "using only the results above."
                    ),
                }
            )

        response_stream = self._create_with_rate_limit_retry(
            model=model,
            messages=messages,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
            **_effort_kwargs(),
            stream=True,
            **extra_kwargs,
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
