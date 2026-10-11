from typing import Any

from app.ai.memory_retriever import MemoryRetriever
from app.ai.tools.base import BaseTool
from app.ai.tools.context import ToolContext


class MemoryTool(BaseTool):
    """
    Search workspace-scoped Vibe memories.

    This tool is specifically for user-specific or
    workspace-specific remembered information.
    It should not be used for general public facts,
    current information, or latest external updates.
    """

    def __init__(
        self,
        context: ToolContext,
    ):
        self.context = context
        self.retriever = MemoryRetriever()

    @property
    def name(self) -> str:
        return "search_memory"

    @property
    def description(self) -> str:
        return (
            "Search the current Vibe workspace memory for "
            "user-specific or workspace-specific information, "
            "such as the user's preferences, goals, projects, "
            "decisions, tasks, previous instructions, or other "
            "remembered context. "
            "Call this tool only when workspace memory is needed. "
            "After receiving a successful result, use that result "
            "to answer the user instead of calling search_memory "
            "again with the same or equivalent query. "
            "Do NOT use this tool for general public facts, "
            "current events, latest information, software releases, "
            "recent changes, or external information. "
            "For current or latest information, use search_web instead. "
            "To list or look up the user's recorded decisions (what was "
            "decided and why), set memory_type to \"decision\"."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": (
                        "The user-specific or workspace-specific "
                        "information to search for in memory."
                    ),
                },
                "memory_type": {
                    "type": ["string", "null"],
                    "description": (
                        "Optional filter: decision, fact, preference, "
                        "goal, project or task. Use decision for "
                        "questions about what was decided and why."
                    ),
                },
            },
            "required": ["query"],
        }

    def execute(
        self,
        query: str,
        memory_type: str | None = None,
    ) -> dict[str, Any]:

        if not query or not query.strip():
            return {
                "success": False,
                "error": "Memory search query cannot be empty.",
            }

        allowed_types = {
            "fact", "preference", "profile", "goal", "decision",
            "task", "knowledge", "summary", "working", "project",
        }

        wanted = (
            memory_type.strip().lower()
            if isinstance(memory_type, str)
            else None
        )

        if wanted not in allowed_types:
            wanted = None

        memories = self.retriever.retrieve(
            db=self.context.db,
            workspace_id=self.context.workspace_id,
            query=query.strip(),
            limit=5,
            memory_type=wanted,
        )

        results = []

        for memory in memories:

            results.append(
                {
                    "id": memory.id,
                    "type": memory.memory_type.value,
                    "title": memory.title,
                    "content": memory.content,
                    "importance": memory.importance,
                    "confidence": memory.confidence,
                }
            )

        return {
            "success": True,
            "query": query.strip(),
            "count": len(results),
            "memories": results,
        }