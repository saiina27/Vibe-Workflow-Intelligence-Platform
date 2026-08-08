from dataclasses import dataclass

from app.ai.provider_mapping import get_provider_for_task
from app.core.config import settings
from app.models.enums import TaskComplexity, TaskType


@dataclass
class RoutingDecision:

    task_type: TaskType
    complexity: TaskComplexity
    provider: str
    model: str
    reason: str


def build_routing_decision(
    task_type: TaskType,
    complexity: TaskComplexity = TaskComplexity.SIMPLE,
) -> RoutingDecision:

    provider = get_provider_for_task(
        task_type,
        complexity,
    )

    if provider == "groq":

        model = (
            settings.groq_model
            or "llama-3.3-70b-versatile"
        )

    elif provider == "gemini":

        model = settings.gemini_model

    else:

        raise ValueError(
            f"Unsupported provider: {provider}"
        )

    reason = (
        f"{complexity.value} {task_type.value} "
        f"tasks are routed to {provider}"
    )

    return RoutingDecision(
        task_type=task_type,
        complexity=complexity,
        provider=provider,
        model=model,
        reason=reason,
    )