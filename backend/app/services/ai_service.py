from collections.abc import Iterator

from app.ai.gateway import AIGateway
from app.ai.task_classifier import task_classifier
from app.ai.tools.context import ToolContext
from app.schemas.ai import AIRequest, AIStreamEvent


gateway = AIGateway()


def generate_ai_response(
    prompt: str,
) -> str:

    task_type = task_classifier.classify(
        prompt
    )

    complexity = task_classifier.classify_complexity(
        prompt
    )

    request = AIRequest(
        prompt=prompt,
        task_type=task_type,
        complexity=complexity,
    )

    response = gateway.generate(
        request
    )

    return response.content or ""


def generate_ai_response_stream(
    prompt: str,
) -> Iterator[str]:
    """
    Stream an AI response incrementally.

    This is the existing text-only streaming path.
    It remains unchanged for backward compatibility.
    """

    task_type = task_classifier.classify(
        prompt
    )

    complexity = task_classifier.classify_complexity(
        prompt
    )

    request = AIRequest(
        prompt=prompt,
        task_type=task_type,
        complexity=complexity,
    )

    yield from gateway.stream(
        request
    )


def generate_ai_response_stream_with_tools(
    prompt: str,
    context: ToolContext,
) -> Iterator[AIStreamEvent]:
    """
    Stream an AI response with real tool-calling events.

    Flow:

        Prompt
          ↓
        Task Classification
          ↓
        AIRequest
          ↓
        AIGateway.stream_with_tools()
          ↓
        AIStreamEvent
          ↓
        content / tool_start / tool_done / tool_error
    """

    task_type = task_classifier.classify(
        prompt
    )

    complexity = task_classifier.classify_complexity(
        prompt
    )

    request = AIRequest(
        prompt=prompt,
        task_type=task_type,
        complexity=complexity,
    )

    yield from gateway.stream_with_tools(
        request=request,
        context=context,
    )


async def generate_ai_response_with_tools(
    prompt: str,
    context: ToolContext,
) -> str:

    task_type = task_classifier.classify(
        prompt
    )

    complexity = task_classifier.classify_complexity(
        prompt
    )

    request = AIRequest(
        prompt=prompt,
        task_type=task_type,
        complexity=complexity,
    )

    response = await gateway.generate_with_tools(
        request=request,
        context=context,
    )

    return response.content or ""
