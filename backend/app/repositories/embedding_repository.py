from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.workspace_memory import (
    MemoryStatus,
    WorkspaceMemory,
)
from app.models.workspace_memory_embedding import (
    WorkspaceMemoryEmbedding,
)


class EmbeddingRepository:

    def create(
        self,
        db: Session,
        memory_id: int,
        embedding: list[float],
        model: str,
    ) -> WorkspaceMemoryEmbedding:

        db_embedding = WorkspaceMemoryEmbedding(
            memory_id=memory_id,
            embedding=embedding,
            model=model,
            dimension=len(embedding),
        )

        db.add(db_embedding)

        db.commit()
        db.refresh(db_embedding)

        return db_embedding

    def similarity_search(
        self,
        db: Session,
        workspace_id: int,
        query_embedding: list[float],
        limit: int = 5,
    ) -> list[WorkspaceMemory]:

        distance = (
            WorkspaceMemoryEmbedding.embedding.cosine_distance(
                query_embedding
            )
        )

        statement = (
            select(WorkspaceMemory)
            .join(
                WorkspaceMemoryEmbedding,
                WorkspaceMemory.id
                == WorkspaceMemoryEmbedding.memory_id,
            )
            .where(
                WorkspaceMemory.workspace_id == workspace_id,
                WorkspaceMemory.status == MemoryStatus.ACTIVE,
                (
                    WorkspaceMemory.expires_at.is_(None)
                    | (
                        WorkspaceMemory.expires_at
                        > datetime.utcnow()
                    )
                ),
            )
            .order_by(distance)
            .limit(limit)
        )

        return list(
            db.scalars(statement).all()
        )

    def find_similar_in_type(
        self,
        db: Session,
        workspace_id: int,
        memory_type,
        query_embedding: list[float],
        limit: int = 1,
    ) -> list[tuple[WorkspaceMemory, float]]:
        """
        Find the closest active memories by embedding cosine
        distance, workspace-wide (memory_type is intentionally
        NOT filtered — the extractor's type classification is
        unstable across near-identical messages, e.g. "fact"
        vs "project" for the same underlying statement, so
        restricting to one type let duplicates slip through).
        Used for semantic duplicate detection during memory
        extraction.

        Returns (memory, distance) pairs — lower distance
        means more similar. Caller converts to similarity
        (1 - distance) and applies its own threshold.
        """

        distance = (
            WorkspaceMemoryEmbedding.embedding.cosine_distance(
                query_embedding
            )
        )

        statement = (
            select(
                WorkspaceMemory,
                distance.label("distance"),
            )
            .join(
                WorkspaceMemoryEmbedding,
                WorkspaceMemory.id
                == WorkspaceMemoryEmbedding.memory_id,
            )
            .where(
                WorkspaceMemory.workspace_id == workspace_id,
                WorkspaceMemory.status == MemoryStatus.ACTIVE,
                (
                    WorkspaceMemory.expires_at.is_(None)
                    | (
                        WorkspaceMemory.expires_at
                        > datetime.utcnow()
                    )
                ),
            )
            .order_by(distance)
            .limit(limit)
        )

        return [
            (row[0], row[1])
            for row in db.execute(statement).all()
        ]

    def update(
        self,
        db: Session,
        memory_id: int,
        embedding: list[float],
        model: str,
    ) -> WorkspaceMemoryEmbedding | None:

        statement = select(
            WorkspaceMemoryEmbedding
        ).where(
            WorkspaceMemoryEmbedding.memory_id == memory_id
        )

        db_embedding = db.scalar(statement)

        if db_embedding is None:
            return None

        db_embedding.embedding = embedding
        db_embedding.model = model
        db_embedding.dimension = len(embedding)

        db.commit()
        db.refresh(db_embedding)

        return db_embedding