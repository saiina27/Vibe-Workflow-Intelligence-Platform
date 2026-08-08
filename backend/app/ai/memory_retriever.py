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
    ) -> list[WorkspaceMemory]:


        query_embedding = (
            self.embedding_service.generate_embedding(
                query
            )
        )


        memories = (
            self.embedding_repository.similarity_search(
                db=db,
                workspace_id=workspace_id,
                query_embedding=query_embedding,
                limit=limit,
            )
        )


        return memories