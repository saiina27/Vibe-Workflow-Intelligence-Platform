from app.models.enums import TaskType


PROVIDER_MAPPING = {
    TaskType.CHAT: "gemini",
    TaskType.CODE: "groq",
    TaskType.DOCUMENT: "gemini",
    TaskType.ANALYSIS: "groq",
    TaskType.DECISION: "groq",
    TaskType.SUGGESTION: "gemini",
    TaskType.MEMORY: "gemini",
    TaskType.SEARCH: "gemini",
    TaskType.IMAGE: "gemini",
    TaskType.UNKNOWN: "gemini",
}


def get_provider_for_task(
    task_type: TaskType,
) -> str:

    return PROVIDER_MAPPING.get(
        task_type,
        "gemini",
    )