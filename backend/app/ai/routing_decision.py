from dataclasses import dataclass

from app.ai.provider_mapping import get_provider_for_task
from app.core.config import settings
from app.models.enums import TaskType


@dataclass
class RoutingDecision:

    task_type: TaskType
    provider: str
    model: str
    reason: str


def build_routing_decision(
    task_type: TaskType,
) -> RoutingDecision:

    provider = get_provider_for_task(
        task_type
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
        f"{task_type.value} tasks are routed "
        f"to {provider}"
    )

    return RoutingDecision(
        task_type=task_type,
        provider=provider,
        model=model,
        reason=reason,
    )