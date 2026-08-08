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