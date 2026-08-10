from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.knowledge_chunk import KnowledgeChunk
from app.models.knowledge_source import (
    KnowledgeSource,
    KnowledgeStatus,
)


class KnowledgeRepository:

    def create_source(
        self,
        db: Session,
        source: KnowledgeSource,
    ) -> KnowledgeSource:

        db.add(source)
        db.commit()
        db.refresh(source)

        return source

    def get_by_id(
        self,
        db: Session,
        source_id: int,
    ) -> KnowledgeSource | None:

        statement = (
            select(KnowledgeSource)
            .where(
                KnowledgeSource.id == source_id,
            )
        )

        return db.scalar(statement)

    def get_workspace_sources(
        self,
        db: Session,
        workspace_id: int,
    ) -> list[KnowledgeSource]:

        statement = (
            select(KnowledgeSource)
            .options(
                selectinload(
                    KnowledgeSource.chunks
                )
            )
            .where(
                KnowledgeSource.workspace_id
                == workspace_id,
            )
            .order_by(
                KnowledgeSource.created_at.desc(),
            )
        )

        return list(
            db.scalars(statement).all()
        )

    def update_status(
        self,
        db: Session,
        source: KnowledgeSource,
        status: KnowledgeStatus,
    ) -> KnowledgeSource:

        source.status = status

        db.commit()
        db.refresh(source)

        return source

    def create_chunks(
        self,
        db: Session,
        chunks: list[KnowledgeChunk],
    ) -> None:

        db.add_all(chunks)
        db.commit()

    def delete(
        self,
        db: Session,
        source: KnowledgeSource,
    ) -> None:

        db.delete(source)
        db.commit()