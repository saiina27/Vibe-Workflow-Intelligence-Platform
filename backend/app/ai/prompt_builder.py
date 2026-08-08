from app.models.conversation_summary import ConversationSummary
from app.models.message import Message
from app.models.workspace_memory import WorkspaceMemory


def build_prompt(
    memories: list[WorkspaceMemory],
    conversation_summary: ConversationSummary | None,
    history: list[Message],
) -> str:

    prompt = ""

    # -------------------------
    # System Context
    # -------------------------

    prompt += """
You are Vibe AI, an intelligent workspace assistant.

Use workspace memories only when they are relevant
to the user's current request.

Do not invent memories.
If memory conflicts exist, prefer newer information.
"""

    # -------------------------
    # Workspace Memory
    # -------------------------

    if memories:

        prompt += (
            "\n=========================\n"
        )

        prompt += (
            "RELEVANT WORKSPACE MEMORY\n"
        )

        prompt += (
            "=========================\n\n"
        )

        for memory in memories:

            prompt += (
                f"Memory Type: {memory.memory_type.value}\n"
            )

            prompt += (
                f"Title: {memory.title}\n"
            )

            prompt += (
                f"Information: {memory.content}\n\n"
            )

    # -------------------------
    # Conversation Summary
    # -------------------------

    if conversation_summary:

        prompt += (
            "=========================\n"
        )

        prompt += (
            "CONVERSATION SUMMARY\n"
        )

        prompt += (
            "=========================\n\n"
        )

        prompt += (
            f"{conversation_summary.summary}\n\n"
        )

    # -------------------------
    # Conversation History
    # -------------------------

    prompt += (
        "=========================\n"
    )

    prompt += (
        "CURRENT CONVERSATION\n"
    )

    prompt += (
        "=========================\n\n"
    )

    for message in history:

        role = message.role.capitalize()

        prompt += (
            f"{role}: {message.content}\n"
        )

    prompt += "\nAssistant:"

    return prompt