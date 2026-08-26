from app.models.conversation_summary import ConversationSummary
from app.models.message import Message
from app.models.workspace_memory import WorkspaceMemory
from app.models.knowledge_chunk import KnowledgeChunk


def build_prompt(
    memories: list[WorkspaceMemory],
    conversation_summary: ConversationSummary | None,
    history: list[Message],
    knowledge_chunks: list[KnowledgeChunk] | None = None,
    include_memories=True,
    include_knowledge=True,
) -> str:

    prompt = ""

    # ========================================================
    # SYSTEM CONTEXT
    # ========================================================

    prompt += """
You are Vibe AI, an intelligent workspace assistant.

You have access to three different information sources:

1. WORKSPACE MEMORY
   - Contains user-specific remembered information.
   - Use it for the user's preferences, goals, projects,
     decisions, tasks, or other persistent workspace context.

2. UPLOADED KNOWLEDGE
   - Contains information from documents uploaded to the
     current workspace.
   - Use it when the user's question is about information
     contained in those documents.

3. WEB SEARCH
   - Searches the public internet.
   - Use it for current, latest, recent, external, or
     time-sensitive information.
   - Use it when the answer may have changed since the
     uploaded documents or workspace memory were created.

IMPORTANT TOOL SELECTION RULES:

- If the user asks for "latest", "current", "recent",
  "today", "new", "updated", or similar time-sensitive
  information about an external topic, prefer WEB SEARCH.

- If the user asks about their own remembered information,
  preferences, goals, projects, or decisions, use WORKSPACE
  MEMORY.

- If the user asks about information contained in uploaded
  documents, use UPLOADED KNOWLEDGE.

- If the user's question requires current public information,
  do NOT rely only on uploaded knowledge or workspace memory.
  Use WEB SEARCH even if retrieved knowledge chunks are present.

- Retrieved knowledge chunks are supporting context. They are
  NOT automatically authoritative for every user question.

- Choose the information source that best matches the user's
  actual question.

- Never claim that information is unavailable merely because
  one information source did not contain it. If another
  appropriate tool is available, use that tool.

- Never invent facts.

- When web search is used, use its returned information to
  answer the user's question.

- When uploaded knowledge is used, stay grounded in the
  retrieved document content.

- When workspace memory is used, stay grounded in the
  retrieved memory content.
"""

    # ========================================================
    # WORKSPACE MEMORY
    # ========================================================

    if include_memories and memories:

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

    # ========================================================
    # UPLOADED KNOWLEDGE
    # ========================================================

    if include_knowledge and knowledge_chunks:

        prompt += (
            "\n=========================\n"
            "RELEVANT UPLOADED KNOWLEDGE\n"
            "=========================\n\n"
        )

        for chunk in knowledge_chunks:

            source = chunk.knowledge_source

            source_filename = (
                source.filename
                if source is not None
                else "Unknown source"
            )

            source_title = (
                source.title
                if source is not None
                else "Unknown title"
            )

            prompt += (
                f"Source: {source_filename}\n"
                f"Title: {source_title}\n"
                f"Chunk: {chunk.chunk_index}\n\n"
                f"{chunk.text}\n\n"
                "-----------------------------\n\n"
            )

    # ========================================================
    # CONVERSATION SUMMARY
    # ========================================================

    if conversation_summary:

        prompt += (
            "=========================\n"
            "CONVERSATION SUMMARY\n"
            "=========================\n\n"
        )

        prompt += (
            f"{conversation_summary.summary}\n\n"
        )

    # ========================================================
    # CURRENT CONVERSATION
    # ========================================================

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

    # ========================================================
    # FINAL INSTRUCTION
    # ========================================================

    prompt += """
=========================
RESPONSE INSTRUCTION
=========================

Determine what information source is appropriate for the
user's request before answering.

If the request asks for current/latest/recent public
information, use WEB SEARCH rather than relying only on
workspace memory or uploaded knowledge.

If a tool is needed, use the appropriate tool first and then
answer using its result.

Assistant:
"""

    return prompt