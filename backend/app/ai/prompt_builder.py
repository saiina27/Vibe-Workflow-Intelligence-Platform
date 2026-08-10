from app.models.conversation_summary import ConversationSummary
from app.models.message import Message
from app.models.workspace_memory import WorkspaceMemory
from app.models.knowledge_chunk import KnowledgeChunk


def build_prompt(
    memories: list[WorkspaceMemory],
    conversation_summary: ConversationSummary | None,
    history: list[Message],
    knowledge_chunks: list[KnowledgeChunk] | None = None,
) -> str:

    prompt = ""

    # -------------------------
    # System Context
    # -------------------------

    prompt += """
You are Vibe AI, an intelligent workspace assistant.

Use workspace memories only when they are relevant
to the user's current request.

Use uploaded knowledge only when it is relevant
to the user's current request.

Answer questions using ONLY the retrieved
knowledge chunks whenever they are available.

Each knowledge chunk contains its source
document information.

Never invent or assume facts that are not
present in the retrieved knowledge.

If the answer is not contained in the
retrieved knowledge, clearly state that
it could not be found in the uploaded
documents.
"""

    # -------------------------
    # Workspace Memory
    # -------------------------

    if memories:

        prompt += (
            "\n=========================\n"
            "RELEVANT WORKSPACE MEMORY\n"
            "=========================\n\n"
        )

        for memory in memories:

            prompt += (
                f"Memory Type: {memory.memory_type.value}\n"
                f"Title: {memory.title}\n"
                f"Information: {memory.content}\n\n"
            )

    # -------------------------
    # Uploaded Knowledge
    # -------------------------

    if knowledge_chunks:

        prompt += (
            "\n=========================\n"
            "RELEVANT UPLOADED KNOWLEDGE\n"
            "=========================\n\n"
        )

        for chunk in knowledge_chunks:

            source = chunk.knowledge_source

            prompt += (
                f"Source: {source.filename}\n"
                f"Title: {source.title}\n"
                f"Chunk: {chunk.chunk_index}\n\n"
                f"{chunk.text}\n\n"
                "-----------------------------\n\n"
            )

    # -------------------------
    # Conversation Summary
    # -------------------------

    if conversation_summary:

        prompt += (
            "=========================\n"
            "CONVERSATION SUMMARY\n"
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
        "CURRENT CONVERSATION\n"
        "=========================\n\n"
    )

    for message in history:

        role = message.role.capitalize()

        prompt += (
            f"{role}: {message.content}\n"
        )

    prompt += "\nAssistant:"

    return prompt