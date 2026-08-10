from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.embedding_service import EmbeddingService
from app.models.workspace_memory import (
    MemorySource,
    MemoryStatus,
    MemoryType,
    WorkspaceMemory,
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

        expires_at = None

        if memory.memory_type == MemoryType.TASK:
            expires_at = (
                datetime.utcnow()
                + timedelta(days=30)
            )

        db_memory = WorkspaceMemory(
            workspace_id=workspace_id,
            memory_type=memory.memory_type,
            title=memory.title,
            content=memory.content,
            importance=memory.importance,
            confidence=0.6,
            source=MemorySource.USER,
            status=MemoryStatus.ACTIVE,
            expires_at=expires_at,
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
            )
            .order_by(
                WorkspaceMemory.importance.desc(),
                WorkspaceMemory.created_at.desc(),
            )
        )

        return list(
            db.scalars(statement).all()
        )

    def get_active_memories(
        self,
        db: Session,
        workspace_id: int,
    ) -> list[WorkspaceMemory]:

        statement = (
            select(WorkspaceMemory)
            .where(
                WorkspaceMemory.workspace_id == workspace_id,
                WorkspaceMemory.status
                == MemoryStatus.ACTIVE,
                (
                    WorkspaceMemory.expires_at.is_(None)
                    | (
                        WorkspaceMemory.expires_at
                        > datetime.utcnow()
                    )
                ),
            )
            .order_by(
                WorkspaceMemory.importance.desc(),
                WorkspaceMemory.created_at.desc(),
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

        statement = (
            select(WorkspaceMemory)
            .where(
                WorkspaceMemory.id == memory_id
            )
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

        content_changed = False

        for key, value in update_data.items():

            if (
                key == "content"
                and db_memory.content != value
            ):
                content_changed = True

            setattr(
                db_memory,
                key,
                value,
            )

        db.commit()
        db.refresh(db_memory)

        if content_changed:

            vector = (
                embedding_service.generate_embedding(
                    db_memory.content
                )
            )

            embedding_repository.update(
                db=db,
                memory_id=db_memory.id,
                embedding=vector,
                model="text-embedding-004",
            )

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
            confidence=1.0,
            source=MemorySource.SYSTEM,
            status=MemoryStatus.ACTIVE,
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

            memory_type = MemoryType(
                memory_data["memory_type"].lower()
                if memory_data["memory_type"].lower()
                in [e.value for e in MemoryType]
                else MemoryType.KNOWLEDGE.value
            )

            expires_at = None

            if memory_type == MemoryType.TASK:
                expires_at = (
                    datetime.utcnow()
                    + timedelta(days=30)
                )

            db_memory = WorkspaceMemory(
                workspace_id=workspace_id,
                memory_type=memory_type,
                title=memory_data["title"],
                content=memory_data["content"],
                importance=memory_data.get(
                    "importance",
                    5,
                ),
                confidence=0.7,
                source=MemorySource.AI,
                status=MemoryStatus.ACTIVE,
                expires_at=expires_at,
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

        memory_type = MemoryType(
            memory_data["memory_type"]
        )

        expires_at = None

        if memory_type == MemoryType.TASK:
            expires_at = (
                datetime.utcnow()
                + timedelta(days=30)
            )

        db_memory = WorkspaceMemory(
            workspace_id=workspace_id,
            memory_type=memory_type,
            title=memory_data["title"],
            content=memory_data["content"],
            importance=memory_data["importance"],
            confidence=0.9,
            source=MemorySource.USER,
            status=MemoryStatus.ACTIVE,
            expires_at=expires_at,
        )

        db.add(db_memory)
        db.commit()
        db.refresh(db_memory)

        self._create_embedding(
            db=db,
            memory=db_memory,
        )

        return db_memory

    def find_by_type_and_title(
        self,
        db: Session,
        workspace_id: int,
        memory_type: MemoryType,
        title: str,
    ) -> WorkspaceMemory | None:

        statement = (
            select(WorkspaceMemory)
            .where(
                WorkspaceMemory.workspace_id
                == workspace_id,
                WorkspaceMemory.memory_type
                == memory_type,
                WorkspaceMemory.status
                == MemoryStatus.ACTIVE,
                WorkspaceMemory.title.ilike(title),
                (
                    WorkspaceMemory.expires_at.is_(None)
                    | (
                        WorkspaceMemory.expires_at
                        > datetime.utcnow()
                    )
                ),
            )
        )

        return db.scalar(statement)