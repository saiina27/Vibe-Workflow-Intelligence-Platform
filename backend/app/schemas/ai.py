from typing import Optional

from pydantic import BaseModel

from app.models.enums import TaskType


class AIRequest(BaseModel):

    prompt: str

    task_type: TaskType = TaskType.UNKNOWN

    model: Optional[str] = None

    temperature: float = 0.7

    max_tokens: int = 1000


class AIResponse(BaseModel):

    content: str

    model: str

    provider: str

    input_tokens: int = 0

    output_tokens: int = 0

    latency_ms: float = 0