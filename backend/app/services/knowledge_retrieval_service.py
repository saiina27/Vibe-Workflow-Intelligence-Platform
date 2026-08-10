from sqlalchemy.orm import Session

from app.ai.embedding_service import EmbeddingService
from app.models.knowledge_chunk import KnowledgeChunk
from app.repositories.knowledge_chunk_repository import (
    KnowledgeChunkRepository,
)


class KnowledgeRetrievalService:

    def __init__(self):

        self.embedding_service = (
            EmbeddingService()
        )

        self.repository = (
            KnowledgeChunkRepository()
        )

    def retrieve(
        self,
        db: Session,
        workspace_id: int,
        query: str,
        top_k: int = 5,
    ) -> list[KnowledgeChunk]:

        query_embedding = (
            self.embedding_service.generate_embedding(
                query
            )
        )

        return self.repository.search_similar(
            db=db,
            workspace_id=workspace_id,
            query_embedding=query_embedding,
            top_k=top_k,
        )