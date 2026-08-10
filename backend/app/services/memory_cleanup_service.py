from datetime import datetime

from sqlalchemy.orm import Session

from app.models.workspace_memory import (
    MemoryStatus,
    WorkspaceMemory,
)


class MemoryCleanupService:

    def expire_memories(
        self,
        db: Session,
    ) -> int:

        expired = (
            db.query(WorkspaceMemory)
            .filter(
                WorkspaceMemory.status == MemoryStatus.ACTIVE,
                WorkspaceMemory.expires_at.is_not(None),
                WorkspaceMemory.expires_at <= datetime.utcnow(),
            )
            .all()
        )

        for memory in expired:
            memory.status = MemoryStatus.EXPIRED

        db.commit()

        return len(expired)


memory_cleanup_service = MemoryCleanupService()