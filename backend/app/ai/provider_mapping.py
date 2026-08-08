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

    # Simple tasks use Gemini.
    if complexity == TaskComplexity.SIMPLE:
        return "gemini"

    # Moderate technical tasks use Groq.
    if complexity == TaskComplexity.MODERATE:
        if task_type in technical_tasks:
            return "groq"

        return "gemini"

    # Complex technical tasks use Groq.
    if complexity == TaskComplexity.COMPLEX:
        if task_type in technical_tasks:
            return "groq"

        return "gemini"

    return "gemini"