import time
from typing import Any

from google import genai
from google.genai import types

from app.ai.providers.base import AIProvider
from app.core.config import settings
from app.schemas.ai import AIRequest, AIResponse, ToolCall


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

        Gemini responses may contain:
            - text
            - function_call
            - function_response
            - thought signatures

        Therefore response.text alone must not be relied upon.
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

        # ----------------------------------------------------
        # SDK fallback
        # ----------------------------------------------------

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
            for tool in request.tools
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

            raise ValueError(
                "Gemini tool configuration requires "
                "at least one tool declaration."
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
    # INITIAL TOOL-CALLING REQUEST
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

        # ----------------------------------------------------
        # INITIAL USER CONTENT
        # ----------------------------------------------------

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

        tool_calls: list[ToolCall] = []

        # ====================================================
        # PARSE GEMINI FUNCTION CALLS
        # ====================================================

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

        # ====================================================
        # DIRECT ANSWER VS TOOL CALL
        # ====================================================

        content = None

        if not tool_calls:

            content = self._extract_text(
                response
            )

        # ====================================================
        # PRESERVE GEMINI CONVERSATION STATE
        # ====================================================

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
    # TOOL RESULT → NEXT GEMINI RESPONSE
    # ========================================================

    def generate_with_tool_results(
        self,
        request: AIRequest,
        original_response: AIResponse,
        tool_results: list[dict[str, Any]],
    ) -> AIResponse:
        """
        Continue the Gemini native tool-calling conversation.

        Supports repeated tool-calling rounds.

        Flow:

            User request
                ↓
            Gemini function call
                ↓
            Application tool execution
                ↓
            Gemini FunctionResponse
                ↓
            Gemini response
                ↓
            Tool call again?
                ↓
            YES → repeat
            NO  → final answer
        """

        start_time = time.time()

        model = (
            request.model
            or settings.gemini_model
        )

        # ====================================================
        # STEP 1: VALIDATE INPUT
        # ====================================================

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

        # ====================================================
        # STEP 2: RESTORE PROVIDER CONTEXT
        # ====================================================

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

        # ====================================================
        # STEP 3: BUILD FUNCTION RESPONSES
        # ====================================================

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

            tool_call_id = (
                tool_result.get(
                    "tool_call_id"
                )
            )

            name = (
                tool_result.get(
                    "name"
                )
            )

            result = (
                tool_result.get(
                    "result"
                )
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

        # ====================================================
        # STEP 4: VALIDATE ALL TOOL RESULTS
        # ====================================================

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

        # ====================================================
        # STEP 5: APPEND FUNCTION RESPONSES
        # ====================================================

        function_response_content = types.Content(
            role="user",
            parts=function_response_parts,
        )

        contents.append(
            function_response_content
        )

        # ====================================================
        # STEP 6: ENABLE TOOLS FOR NEXT ROUND
        # ====================================================

        config = self._build_tool_config(
            request
        )

        # ====================================================
        # STEP 7: GEMINI NEXT RESPONSE
        # ====================================================

        response = self.client.models.generate_content(
            model=model,
            contents=contents,
            config=config,
        )

        latency = (
            time.time() - start_time
        ) * 1000

        # ====================================================
        # STEP 8: PARSE NEXT TOOL CALLS
        # ====================================================

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

        # ====================================================
        # STEP 9: UPDATE PROVIDER CONTEXT
        # ====================================================

        updated_context = list(
            contents
        )

        for candidate in response.candidates or []:

            if candidate.content:

                updated_context.append(
                    candidate.content
                )

        # ====================================================
        # STEP 10: FINAL ANSWER VS NEXT TOOL CALL
        # ====================================================

        content = None

        if not tool_calls:

            content = self._extract_text(
                response
            )

        # ====================================================
        # STEP 11: VALIDATE FINAL RESPONSE
        # ====================================================

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

        # ====================================================
        # STEP 12: RETURN RESPONSE
        # ====================================================

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