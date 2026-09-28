import time
from collections.abc import Iterator
from typing import Any

from google import genai
from google.genai import types

from app.ai.providers.base import AIProvider
from app.core.config import settings
from app.schemas.ai import (
    AIRequest,
    AIResponse,
    AIStreamEvent,
    ToolCall,
)


class GeminiProvider(AIProvider):

    def __init__(self):

        self.client = genai.Client(
            api_key=settings.gemini_api_key
        )

    # ========================================================
    # RESPONSE TEXT EXTRACTION
    # ========================================================

    @staticmethod
    def _extract_text(
        response: Any,
    ) -> str:
        """
        Safely extract all text parts from a Gemini response.
        """

        content_parts: list[str] = []

        for candidate in response.candidates or []:

            if not candidate.content:
                continue

            for part in candidate.content.parts or []:

                text = getattr(
                    part,
                    "text",
                    None,
                )

                if text:
                    content_parts.append(text)

        content = "\n".join(
            content_parts
        ).strip()

        if content:
            return content

        try:

            sdk_text = response.text

            if sdk_text:
                return sdk_text.strip()

        except Exception:
            pass

        return ""

    # ========================================================
    # USAGE HELPERS
    # ========================================================

    @staticmethod
    def _input_tokens(
        response: Any,
    ) -> int:

        usage = response.usage_metadata

        if not usage:
            return 0

        return (
            usage.prompt_token_count
            or 0
        )

    @staticmethod
    def _output_tokens(
        response: Any,
    ) -> int:

        usage = response.usage_metadata

        if not usage:
            return 0

        return (
            usage.candidates_token_count
            or 0
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
            or settings.gemini_model
        )

        response = self.client.models.generate_content(
            model=model,
            contents=request.prompt,
        )

        latency = (
            time.time() - start_time
        ) * 1000

        content = self._extract_text(
            response
        )

        return AIResponse(
            content=content,
            model=model,
            provider="gemini",
            input_tokens=self._input_tokens(
                response
            ),
            output_tokens=self._output_tokens(
                response
            ),
            latency_ms=latency,
            provider_response=response,
        )

    # ========================================================
    # NORMAL STREAMING GENERATION
    # ========================================================

    def stream(
        self,
        request: AIRequest,
    ) -> Iterator[str]:

        model = (
            request.model
            or settings.gemini_model
        )

        response_stream = (
            self.client.models.generate_content_stream(
                model=model,
                contents=request.prompt,
                config=types.GenerateContentConfig(
                    temperature=request.temperature,
                    maxOutputTokens=request.max_tokens,
                ),
            )
        )

        for chunk in response_stream:

            text = getattr(
                chunk,
                "text",
                None,
            )

            if text:
                yield text

    # ========================================================
    # TOOL DECLARATIONS
    # ========================================================

    def _build_tool_declarations(
        self,
        request: AIRequest,
    ) -> list[types.FunctionDeclaration]:

        return [
            types.FunctionDeclaration(
                name=tool.name,
                description=tool.description,
                parametersJsonSchema=tool.parameters,
            )
            for tool in (request.tools or [])
        ]

    # ========================================================
    # TOOL CONFIGURATION
    # ========================================================

    def _build_tool_config(
        self,
        request: AIRequest,
    ) -> types.GenerateContentConfig:

        declarations = (
            self._build_tool_declarations(
                request
            )
        )

        if not declarations:

            # Final round: no tools, so Gemini must answer
            # in plain text.
            return types.GenerateContentConfig(
                temperature=request.temperature,
                maxOutputTokens=request.max_tokens,
            )

        return types.GenerateContentConfig(
            temperature=request.temperature,
            maxOutputTokens=request.max_tokens,
            tools=[
                types.Tool(
                    functionDeclarations=declarations
                )
            ],
        )

    # ========================================================
    # GEMINI FUNCTION CALL PARSER
    # ========================================================

    @staticmethod
    def _parse_function_calls(
        response: Any,
    ) -> list[ToolCall]:

        tool_calls: list[ToolCall] = []

        for candidate in response.candidates or []:

            if not candidate.content:
                continue

            for part in candidate.content.parts or []:

                function_call = getattr(
                    part,
                    "function_call",
                    None,
                )

                if not function_call:
                    continue

                if not function_call.name:
                    continue

                raw_arguments = (
                    function_call.args
                    or {}
                )

                if not isinstance(
                    raw_arguments,
                    dict,
                ):

                    try:

                        raw_arguments = dict(
                            raw_arguments
                        )

                    except (
                        TypeError,
                        ValueError,
                    ) as exc:

                        raise ValueError(
                            f"Invalid arguments returned "
                            f"for Gemini tool "
                            f"'{function_call.name}'."
                        ) from exc

                tool_calls.append(
                    ToolCall(
                        id=(
                            function_call.id
                            or (
                                f"call_"
                                f"{len(tool_calls) + 1}"
                            )
                        ),
                        name=function_call.name,
                        arguments=raw_arguments,
                    )
                )

        return tool_calls

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
            or settings.gemini_model
        )

        config = self._build_tool_config(
            request
        )

        user_content = types.Content(
            role="user",
            parts=[
                types.Part(
                    text=request.prompt
                )
            ],
        )

        response = self.client.models.generate_content(
            model=model,
            contents=[
                user_content
            ],
            config=config,
        )

        latency = (
            time.time() - start_time
        ) * 1000

        tool_calls = self._parse_function_calls(
            response
        )

        content = None

        if not tool_calls:

            content = self._extract_text(
                response
            )

        provider_context: list[Any] = [
            user_content
        ]

        for candidate in response.candidates or []:

            if candidate.content:

                provider_context.append(
                    candidate.content
                )

        return AIResponse(
            content=content,
            model=model,
            provider="gemini",
            input_tokens=self._input_tokens(
                response
            ),
            output_tokens=self._output_tokens(
                response
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
        Stream a Gemini response with native tool calling.

        Text is emitted incrementally as content events.

        Function calls are collected from the streamed
        response and emitted as a tool_call event once the
        provider has produced the complete response.

        Provider context is preserved inside the event so the
        ToolCallingService can continue the same conversation.
        """

        start_time = time.time()

        model = (
            request.model
            or settings.gemini_model
        )

        config = self._build_tool_config(
            request
        )

        user_content = types.Content(
            role="user",
            parts=[
                types.Part(
                    text=request.prompt
                )
            ],
        )

        response_stream = (
            self.client.models.generate_content_stream(
                model=model,
                contents=[
                    user_content
                ],
                config=config,
            )
        )

        candidates: list[Any] = []
        text_chunks: list[str] = []

        for chunk in response_stream:

            for candidate in chunk.candidates or []:

                candidates.append(candidate)

                if not candidate.content:
                    continue

                for part in candidate.content.parts or []:

                    text = getattr(
                        part,
                        "text",
                        None,
                    )

                    if text:
                        text_chunks.append(text)

                        yield AIStreamEvent(
                            type="content",
                            text=text,
                            model=model,
                            provider="gemini",
                        )

        # ----------------------------------------------------
        # Reconstruct the provider response context.
        #
        # Each streamed candidate may represent a partial
        # response, so we preserve the candidate contents
        # exactly as returned by Gemini.
        # ----------------------------------------------------

        provider_context: list[Any] = [
            user_content
        ]

        seen_candidate_objects: set[int] = set()

        for candidate in candidates:

            if not candidate.content:
                continue

            candidate_identity = id(
                candidate.content
            )

            if candidate_identity in seen_candidate_objects:
                continue

            seen_candidate_objects.add(
                candidate_identity
            )

            provider_context.append(
                candidate.content
            )

        # ----------------------------------------------------
        # Build a lightweight response object containing the
        # complete streamed candidate data.
        # ----------------------------------------------------

        tool_calls: list[ToolCall] = []

        for candidate in candidates:

            if not candidate.content:
                continue

            for part in candidate.content.parts or []:

                function_call = getattr(
                    part,
                    "function_call",
                    None,
                )

                if not function_call:
                    continue

                if not function_call.name:
                    continue

                raw_arguments = (
                    function_call.args
                    or {}
                )

                if not isinstance(
                    raw_arguments,
                    dict,
                ):

                    try:

                        raw_arguments = dict(
                            raw_arguments
                        )

                    except (
                        TypeError,
                        ValueError,
                    ) as exc:

                        raise ValueError(
                            f"Invalid arguments returned "
                            f"for Gemini tool "
                            f"'{function_call.name}'."
                        ) from exc

                tool_calls.append(
                    ToolCall(
                        id=(
                            function_call.id
                            or (
                                f"call_"
                                f"{len(tool_calls) + 1}"
                            )
                        ),
                        name=function_call.name,
                        arguments=raw_arguments,
                    )
                )

        if tool_calls:

            yield AIStreamEvent(
                type="tool_call",
                tool_calls=tool_calls,
                model=model,
                provider="gemini",
                provider_context=provider_context,
            )

    # ========================================================
    # TOOL RESULT → NEXT GEMINI RESPONSE
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
            or settings.gemini_model
        )

        if not tool_results:

            raise ValueError(
                "Gemini tool-result round-trip requires "
                "at least one tool result."
            )

        if not original_response.tool_calls:

            raise ValueError(
                "Original Gemini response contains "
                "no tool calls."
            )

        previous_context = (
            original_response.provider_context
        )

        if not previous_context:

            raise ValueError(
                "Gemini provider conversation context "
                "is missing."
            )

        contents: list[Any] = list(
            previous_context
        )

        function_response_parts: list[
            types.Part
        ] = []

        seen_tool_call_ids: set[str] = set()

        expected_tool_call_ids = {
            tool_call.id
            for tool_call in (
                original_response.tool_calls
            )
            if tool_call.id
        }

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

            if result is None:

                raise ValueError(
                    f"Tool result for '{name}' "
                    "is missing 'result'."
                )

            if tool_call_id in seen_tool_call_ids:

                raise ValueError(
                    f"Duplicate tool result for "
                    f"tool call '{tool_call_id}'."
                )

            if expected_tool_call_ids and (
                tool_call_id
                not in expected_tool_call_ids
            ):

                raise ValueError(
                    f"Tool result references unknown "
                    f"Gemini tool call ID "
                    f"'{tool_call_id}'."
                )

            seen_tool_call_ids.add(
                tool_call_id
            )

            function_response_parts.append(
                types.Part(
                    function_response=(
                        types.FunctionResponse(
                            id=tool_call_id,
                            name=name,
                            response={
                                "result": result,
                            },
                        )
                    )
                )
            )

        missing_tool_call_ids = (
            expected_tool_call_ids
            - seen_tool_call_ids
        )

        if missing_tool_call_ids:

            raise ValueError(
                "Missing Gemini tool results for "
                f"tool call IDs: "
                f"{sorted(missing_tool_call_ids)}"
            )

        function_response_content = types.Content(
            role="user",
            parts=function_response_parts,
        )

        contents.append(
            function_response_content
        )

        config = self._build_tool_config(
            request
        )

        response = self.client.models.generate_content(
            model=model,
            contents=contents,
            config=config,
        )

        latency = (
            time.time() - start_time
        ) * 1000

        tool_calls = self._parse_function_calls(
            response
        )

        updated_context = list(
            contents
        )

        for candidate in response.candidates or []:

            if candidate.content:

                updated_context.append(
                    candidate.content
                )

        content = None

        if not tool_calls:

            content = self._extract_text(
                response
            )

        if not tool_calls and not content:

            candidate_count = len(
                response.candidates
                or []
            )

            raise RuntimeError(
                "Gemini returned neither a tool call "
                "nor final text after tool execution. "
                f"Candidates: {candidate_count}."
            )

        return AIResponse(
            content=content,
            model=model,
            provider="gemini",
            input_tokens=self._input_tokens(
                response
            ),
            output_tokens=self._output_tokens(
                response
            ),
            latency_ms=latency,
            tool_calls=tool_calls,
            provider_response=response,
            provider_context=updated_context,
        )

    # ========================================================
    # STREAMING TOOL RESULT → NEXT GEMINI RESPONSE
    # ========================================================

    def stream_with_tool_results(
        self,
        request: AIRequest,
        original_response: AIResponse,
        tool_results: list[dict[str, Any]],
    ) -> Iterator[AIStreamEvent]:
        """
        Stream the Gemini response after tool execution.

        The original provider context is restored so the
        streamed response remains part of the same native
        Gemini tool-calling conversation.
        """

        model = (
            request.model
            or settings.gemini_model
        )

        if not tool_results:

            raise ValueError(
                "Gemini streaming tool-result round-trip "
                "requires at least one tool result."
            )

        if not original_response.tool_calls:

            raise ValueError(
                "Original Gemini response contains "
                "no tool calls."
            )

        previous_context = (
            original_response.provider_context
        )

        if not previous_context:

            raise ValueError(
                "Gemini provider conversation context "
                "is missing."
            )

        contents: list[Any] = list(
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

        function_response_parts: list[
            types.Part
        ] = []

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
                    f"Gemini tool call ID "
                    f"'{tool_call_id}'."
                )

            seen_tool_call_ids.add(
                tool_call_id
            )

            function_response_parts.append(
                types.Part(
                    function_response=(
                        types.FunctionResponse(
                            id=tool_call_id,
                            name=name,
                            response={
                                "result": result,
                            },
                        )
                    )
                )
            )

        missing_tool_call_ids = (
            expected_tool_call_ids
            - seen_tool_call_ids
        )

        if missing_tool_call_ids:

            raise ValueError(
                "Missing Gemini tool results for "
                f"tool call IDs: "
                f"{sorted(missing_tool_call_ids)}"
            )

        contents.append(
            types.Content(
                role="user",
                parts=function_response_parts,
            )
        )

        config = self._build_tool_config(
            request
        )

        response_stream = (
            self.client.models.generate_content_stream(
                model=model,
                contents=contents,
                config=config,
            )
        )

        collected_candidates: list[Any] = []

        for chunk in response_stream:

            for candidate in chunk.candidates or []:

                collected_candidates.append(
                    candidate
                )

                if not candidate.content:
                    continue

                for part in candidate.content.parts or []:

                    text = getattr(
                        part,
                        "text",
                        None,
                    )

                    if text:

                        yield AIStreamEvent(
                            type="content",
                            text=text,
                            model=model,
                            provider="gemini",
                        )

        tool_calls: list[ToolCall] = []

        for candidate in collected_candidates:

            if not candidate.content:
                continue

            for part in candidate.content.parts or []:

                function_call = getattr(
                    part,
                    "function_call",
                    None,
                )

                if not function_call:
                    continue

                if not function_call.name:
                    continue

                raw_arguments = (
                    function_call.args
                    or {}
                )

                if not isinstance(
                    raw_arguments,
                    dict,
                ):

                    try:

                        raw_arguments = dict(
                            raw_arguments
                        )

                    except (
                        TypeError,
                        ValueError,
                    ) as exc:

                        raise ValueError(
                            f"Invalid arguments returned "
                            f"for Gemini tool "
                            f"'{function_call.name}'."
                        ) from exc

                tool_calls.append(
                    ToolCall(
                        id=(
                            function_call.id
                            or (
                                f"call_"
                                f"{len(tool_calls) + 1}"
                            )
                        ),
                        name=function_call.name,
                        arguments=raw_arguments,
                    )
                )

        if tool_calls:

            updated_context = list(
                contents
            )

            for candidate in collected_candidates:

                if candidate.content:

                    updated_context.append(
                        candidate.content
                    )

            yield AIStreamEvent(
                type="tool_call",
                tool_calls=tool_calls,
                model=model,
                provider="gemini",
                provider_context=updated_context,
            )
