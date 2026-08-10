
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models.knowledge_chunk import KnowledgeChunk


class KnowledgeChunkRepository:

    def create_many(
        self,
        db: Session,
        chunks: list[KnowledgeChunk],
    ) -> None:

        db.add_all(chunks)
        db.commit()

    def get_by_source(
        self,
        db: Session,
        source_id: int,
    ) -> list[KnowledgeChunk]:

        statement = (
            select(KnowledgeChunk)
            .where(
                KnowledgeChunk.knowledge_source_id
                == source_id,
            )
            .order_by(
                KnowledgeChunk.chunk_index,
            )
        )

        return list(
            db.scalars(statement).all()
        )

    def search_similar(
        self,
        db: Session,
        workspace_id: int,
        query_embedding: list[float],
        top_k: int = 5,
        similarity_threshold: float = 0.35,
    ) -> list[KnowledgeChunk]:

        if not query_embedding:
            return []

        if top_k <= 0:
            return []

        distance = (
            KnowledgeChunk.embedding.cosine_distance(
                query_embedding
            )
        )

        # Cosine similarity = 1 - cosine distance
        similarity = 1 - distance

        statement = (
            select(KnowledgeChunk)
            .options(
                joinedload(
                    KnowledgeChunk.knowledge_source
                )
            )
            .where(
                KnowledgeChunk.workspace_id
                == workspace_id,
                KnowledgeChunk.embedding.is_not(None),
                similarity >= similarity_threshold,
            )
            .order_by(
                distance,
            )
            .limit(top_k)
        )

        return list(
            db.scalars(statement).all()
        )

    def delete_by_source(
        self,
        db: Session,
        source_id: int,
    ) -> None:

        statement = (
            select(KnowledgeChunk)
            .where(
                KnowledgeChunk.knowledge_source_id
                == source_id,
            )
        )

        chunks = list(
            db.scalars(statement).all()
        )

        for chunk in chunks:
            db.delete(chunk)

        db.commit()

