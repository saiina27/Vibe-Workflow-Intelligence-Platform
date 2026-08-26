from typing import Any

from app.ai.knowledge_retriever import KnowledgeRetriever
from app.ai.tools.base import BaseTool
from app.ai.tools.context import ToolContext


class KnowledgeTool(BaseTool):
    """
    Search workspace-scoped knowledge sources using
    semantic vector retrieval.
    """

    def __init__(
        self,
        context: ToolContext,
    ):
        self.context = context
        self.retriever = KnowledgeRetriever()

    @property
    def name(self) -> str:
        return "search_knowledge"

    @property
    def description(self) -> str:
        return (
            "Search the current Vibe workspace knowledge base "
            "for relevant information from uploaded documents "
            "and other indexed knowledge sources."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": (
                        "The information to search for "
                        "in the workspace knowledge base."
                    ),
                },
            },
            "required": ["query"],
        }

    def execute(
        self,
        query: str,
    ) -> dict[str, Any]:

        if not query or not query.strip():
            return {
                "success": False,
                "error": "Knowledge search query cannot be empty.",
            }

        chunks = self.retriever.retrieve(
            db=self.context.db,
            workspace_id=self.context.workspace_id,
            query=query.strip(),
            limit=5,
        )

        results = []

        for chunk in chunks:
            source = chunk.knowledge_source

            results.append(
                {
                    "chunk_id": chunk.id,
                    "source_id": chunk.knowledge_source_id,
                    "source_title": (
                        source.title
                        if source is not None
                        else None
                    ),
                    "filename": (
                        source.filename
                        if source is not None
                        else None
                    ),
                    "chunk_index": chunk.chunk_index,
                    "text": chunk.text,
                    "metadata": chunk.chunk_metadata,
                }
            )

        return {
            "success": True,
            "query": query.strip(),
            "count": len(results),
            "chunks": results,
        }
