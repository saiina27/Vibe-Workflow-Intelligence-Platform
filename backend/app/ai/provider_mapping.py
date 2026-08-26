from app.models.enums import TaskComplexity, TaskType


def get_provider_for_task(
    task_type: TaskType,
    complexity: TaskComplexity = TaskComplexity.SIMPLE,
) -> str:

    technical_tasks = {
        TaskType.CODE,
        TaskType.ANALYSIS,
        TaskType.DECISION,
    }

    # ========================================================
    # SIMPLE TECHNICAL TASKS
    # ========================================================
    # Tool-calling / technical tasks should use Groq
    # so Gemini free-tier quota is not consumed by
    # the tool round-trip.
    if complexity == TaskComplexity.SIMPLE:

        if task_type in technical_tasks:
            return "groq"

        return "gemini"

    # ========================================================
    # MODERATE TECHNICAL TASKS
    # ========================================================

    if complexity == TaskComplexity.MODERATE:

        if task_type in technical_tasks:
            return "groq"

        return "gemini"

    # ========================================================
    # COMPLEX TECHNICAL TASKS
    # ========================================================

    if complexity == TaskComplexity.COMPLEX:

        if task_type in technical_tasks:
            return "groq"

        return "gemini"

    return "gemini"