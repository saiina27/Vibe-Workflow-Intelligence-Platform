from sqlalchemy.orm import Session

from app.ai.embedding_service import EmbeddingService
from app.models.workspace_memory import WorkspaceMemory
from app.repositories.embedding_repository import (
    EmbeddingRepository,
)


class MemoryRetriever:

    def __init__(self):

        self.embedding_service = EmbeddingService()

        self.embedding_repository = (
            EmbeddingRepository()
        )

    def retrieve(
        self,
        db: Session,
        workspace_id: int,
        query: str,
        limit: int = 5,
        memory_type: str | None = None,
    ) -> list[WorkspaceMemory]:
        """
        Semantic memory search. With memory_type (for example
        "decision"), only memories of that type are returned: more
        candidates are fetched, then filtered.
        """

        query_embedding = (
            self.embedding_service.generate_embedding(
                query
            )
        )

        fetch_limit = limit * 4 if memory_type else limit

        memories = (
            self.embedding_repository.similarity_search(
                db=db,
                workspace_id=workspace_id,
                query_embedding=query_embedding,
                limit=fetch_limit,
            )
        )

        if memory_type:
            memories = [
                m
                for m in memories
                if getattr(m.memory_type, "value", m.memory_type)
                == memory_type
            ][:limit]

        return memories
