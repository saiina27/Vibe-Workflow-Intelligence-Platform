from sqlalchemy.orm import Session

from app.models.workspace_memory import WorkspaceMemory
from app.repositories.memory_repository import MemoryRepository
from app.schemas.workspace_memory import (
    MemoryCreate,
    MemoryUpdate,
)


class MemoryService:

    def __init__(self):
        self.repository = MemoryRepository()

    def create_memory(
        self,
        db: Session,
        workspace_id: int,
        memory: MemoryCreate,
    ) -> WorkspaceMemory:

        return self.repository.create(
            db=db,
            workspace_id=workspace_id,
            memory=memory,
        )

    def get_workspace_memories(
        self,
        db: Session,
        workspace_id: int,
    ) -> list[WorkspaceMemory]:

        return self.repository.get_by_workspace(
            db=db,
            workspace_id=workspace_id,
        )

    def get_active_memories(
        self,
        db: Session,
        workspace_id: int,
    ) -> list[WorkspaceMemory]:

        return self.repository.get_active_memories(
            db=db,
            workspace_id=workspace_id,
        )

    def get_memory(
        self,
        db: Session,
        memory_id: int,
    ) -> WorkspaceMemory | None:

        return self.repository.get_by_id(
            db=db,
            memory_id=memory_id,
        )

    def update_memory(
        self,
        db: Session,
        memory_id: int,
        memory: MemoryUpdate,
    ) -> WorkspaceMemory | None:

        db_memory = self.repository.get_by_id(
            db=db,
            memory_id=memory_id,
        )

        if db_memory is None:
            return None

        return self.repository.update(
            db=db,
            db_memory=db_memory,
            memory=memory,
        )

    def update_existing_memory(
        self,
        db: Session,
        db_memory: WorkspaceMemory,
        memory: MemoryCreate,
    ) -> WorkspaceMemory:

        update = MemoryUpdate(
            title=memory.title,
            content=memory.content,
            importance=memory.importance,
        )

        return self.repository.update(
            db=db,
            db_memory=db_memory,
            memory=update,
        )

    def delete_memory(
        self,
        db: Session,
        memory_id: int,
    ) -> bool:

        db_memory = self.repository.get_by_id(
            db=db,
            memory_id=memory_id,
        )

        if db_memory is None:
            return False

        self.repository.delete(
            db=db,
            db_memory=db_memory,
        )

        return True


    def increase_confidence(
        self,
        db: Session,
        db_memory: WorkspaceMemory,
        amount: float = 0.05,
    ) -> WorkspaceMemory:

        db_memory.confidence = min(
        1.0,
        db_memory.confidence + amount,
        )

        db.commit()
        db.refresh(db_memory)

        return db_memory