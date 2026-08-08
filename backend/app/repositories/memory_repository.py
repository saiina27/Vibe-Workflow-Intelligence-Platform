from sqlalchemy import select
from sqlalchemy.orm import Session
from datetime import datetime

from app.ai.embedding_service import EmbeddingService
from app.models.workspace_memory import (
    WorkspaceMemory,
    MemoryType,
    MemorySource,
    MemoryStatus,
)
from app.repositories.embedding_repository import EmbeddingRepository
from app.schemas.workspace_memory import (
    MemoryCreate,
    MemoryUpdate,
)


embedding_service = EmbeddingService()
embedding_repository = EmbeddingRepository()


class MemoryRepository:

    def _create_embedding(
        self,
        db: Session,
        memory: WorkspaceMemory,
    ) -> None:

        vector = embedding_service.generate_embedding(
            memory.content
        )

        embedding_repository.create(
            db=db,
            memory_id=memory.id,
            embedding=vector,
            model="text-embedding-004",
        )


    def create(
        self,
        db: Session,
        workspace_id: int,
        memory: MemoryCreate,
    ) -> WorkspaceMemory:

        db_memory = WorkspaceMemory(
            workspace_id=workspace_id,
            memory_type=memory.memory_type,
            title=memory.title,
            content=memory.content,
            importance=memory.importance,
            confidence=1.0,
            source=MemorySource.USER,
            status=MemoryStatus.ACTIVE,
        )

        db.add(db_memory)

        db.commit()

        db.refresh(db_memory)

        self._create_embedding(
            db=db,
            memory=db_memory,
        )

        return db_memory


    def get_by_workspace(
        self,
        db: Session,
        workspace_id: int,
    ) -> list[WorkspaceMemory]:

        statement = (
            select(WorkspaceMemory)
            .where(
                WorkspaceMemory.workspace_id == workspace_id,
                WorkspaceMemory.status == MemoryStatus.ACTIVE,
                (
                    WorkspaceMemory.expires_at.is_(None)
                    | (WorkspaceMemory.expires_at > datetime.utcnow())
                ),
            )
            .order_by(
                WorkspaceMemory.importance.desc()
            )
        )

        return list(
            db.scalars(statement).all()
        )

    def get_by_id(
        self,
        db: Session,
        memory_id: int,
    ) -> WorkspaceMemory | None:

        statement = select(
            WorkspaceMemory
        ).where(
            WorkspaceMemory.id == memory_id
        )

        return db.scalar(statement)


    def update(
        self,
        db: Session,
        db_memory: WorkspaceMemory,
        memory: MemoryUpdate,
    ) -> WorkspaceMemory:

        update_data = memory.model_dump(
            exclude_unset=True
        )

        for key, value in update_data.items():

            setattr(
                db_memory,
                key,
                value,
            )

        db.commit()

        db.refresh(db_memory)

        return db_memory


    def delete(
        self,
        db: Session,
        db_memory: WorkspaceMemory,
    ) -> None:

        db.delete(db_memory)

        db.commit()


    def create_summary(
        self,
        db: Session,
        workspace_id: int,
        summary: str,
    ) -> WorkspaceMemory:

        memory = WorkspaceMemory(
            workspace_id=workspace_id,
            memory_type=MemoryType.SUMMARY,
            title="Conversation Summary",
            content=summary,
            importance=10,
            source=MemorySource.SYSTEM,
        )

        db.add(memory)

        db.commit()

        db.refresh(memory)

        self._create_embedding(
            db=db,
            memory=memory,
        )

        return memory


    def create_multiple_ai_memories(
        self,
        db: Session,
        workspace_id: int,
        memories: list[dict],
    ) -> list[WorkspaceMemory]:

        created_memories = []

        for memory_data in memories:

            db_memory = WorkspaceMemory(
                workspace_id=workspace_id,
                memory_type=MemoryType(
                    memory_data["memory_type"].lower()
                    if memory_data["memory_type"].lower()
                    in [e.value for e in MemoryType]
                    else MemoryType.KNOWLEDGE.value
                ),

                title=memory_data["title"],
                content=memory_data["content"],
                importance=memory_data.get(
                    "importance",
                    5,
                ),
                source=MemorySource.AI,
            )

            db.add(db_memory)

            db.commit()

            db.refresh(db_memory)

            self._create_embedding(
                db=db,
                memory=db_memory,
            )

            created_memories.append(
                db_memory
            )

        return created_memories


    def create_ai_memory(
        self,
        db: Session,
        workspace_id: int,
        memory_data: dict,
    ) -> WorkspaceMemory:

        db_memory = WorkspaceMemory(
            workspace_id=workspace_id,
            memory_type=MemoryType(
                memory_data["memory_type"]
            ),
            title=memory_data["title"],
            content=memory_data["content"],
            importance=memory_data["importance"],
            source=MemorySource.USER,
        )

        db.add(db_memory)

        db.commit()

        db.refresh(db_memory)

        self._create_embedding(
            db=db,
            memory=db_memory,
        )

        return db_memory