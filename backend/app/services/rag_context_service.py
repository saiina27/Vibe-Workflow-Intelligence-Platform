from sqlalchemy.orm import Session

from app.ai.embedding_service import EmbeddingService
from app.repositories.knowledge_chunk_repository import (
    KnowledgeChunkRepository,
)


class RAGContextService:

    def __init__(self):

        self.embedding_service = (
            EmbeddingService()
        )

        self.chunk_repository = (
            KnowledgeChunkRepository()
        )

    def build_context(
        self,
        db: Session,
        workspace_id: int,
        query: str,
        top_k: int = 5,
    ) -> str:

        query_embedding = (
            self.embedding_service.generate_embedding(
                query
            )
        )

        chunks = (
            self.chunk_repository.search_similar(
                db=db,
                workspace_id=workspace_id,
                query_embedding=query_embedding,
                top_k=top_k,
            )
        )

        if not chunks:
            return ""

        context_parts = []

        for index, chunk in enumerate(
            chunks,
            start=1,
        ):

            context_parts.append(
                f"[Source {index}]\n"
                f"{chunk.text}"
            )

        return "\n\n".join(
            context_parts
        )