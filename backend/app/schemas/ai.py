from typing import Any, Optional

from pydantic import BaseModel, Field

from app.models.enums import TaskComplexity, TaskType


class ToolCall(BaseModel):
    """
    Represents a tool invocation requested by an AI provider.
    """

    id: str

    name: str

    arguments: dict[str, Any] = Field(
        default_factory=dict
    )


class ToolDefinition(BaseModel):
    """
    Provider-independent definition of an AI tool.
    """

    name: str

    description: str

    parameters: dict[str, Any]


class ToolResult(BaseModel):
    """
    Result returned after executing a tool.
    """

    tool_call_id: str

    name: str

    result: Any


class AIRequest(BaseModel):
    """
    Provider-independent AI generation request.
    """

    prompt: str

    task_type: TaskType = TaskType.UNKNOWN

    complexity: TaskComplexity = TaskComplexity.SIMPLE

    model: Optional[str] = None

    temperature: float = 0.7

    max_tokens: int = 1000

    tools: list[ToolDefinition] = Field(
        default_factory=list
    )


class AIResponse(BaseModel):
    """
    Provider-independent AI generation response.

    provider_response:
        Raw native provider response.

    provider_context:
        Provider-specific conversation state required for
        multi-round tool calling.
    """

    content: str | None = None

    model: str

    provider: str

    input_tokens: int = 0

    output_tokens: int = 0

    latency_ms: float = 0

    tool_calls: list[ToolCall] = Field(
        default_factory=list
    )

    provider_response: Any | None = None

    provider_context: list[Any] = Field(
        default_factory=list
    )