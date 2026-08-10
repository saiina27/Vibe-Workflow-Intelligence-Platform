
from sqlalchemy.orm import Session

from app.ai.embedding_service import EmbeddingService
from app.repositories.knowledge_chunk_repository import (
    KnowledgeChunkRepository,
)


class KnowledgeRetriever:

    def __init__(self):
        self.embedding_service = EmbeddingService()
        self.repository = KnowledgeChunkRepository()

    def retrieve(
        self,
        db: Session,
        workspace_id: int,
        query: str,
        limit: int = 5,
    ):
        """
        Retrieve the most relevant knowledge chunks for a query
        within a specific workspace.
        """

        if not query or not query.strip():
            return []

        if limit <= 0:
            return []

        query_embedding = self.embedding_service.generate_embedding(
            query.strip()
        )

        if not query_embedding:
            return []

        chunks = self.repository.search_similar(
            db=db,
            workspace_id=workspace_id,
            query_embedding=query_embedding,
            top_k=limit,
        )

        print("=" * 60)
        print("RAG RETRIEVAL")
        print(f"Workspace ID: {workspace_id}")
        print(f"Query: {query.strip()}")
        print(f"Requested Top-K: {limit}")
        print(f"Retrieved Chunks: {len(chunks)}")

        for index, chunk in enumerate(chunks, start=1):
            print(
                f"[{index}] "
                f"chunk_id={chunk.id} "
                f"chunk_index={chunk.chunk_index}"
            )

        print("=" * 60)

        return chunks

