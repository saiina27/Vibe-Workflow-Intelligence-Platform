from sqlalchemy.orm import Session

from app.models.workspace_memory import WorkspaceMemory
from app.schemas.workspace_memory import MemoryCreate
from app.services.memory_service import MemoryService


class MemoryDecisionService:

    def __init__(self):
        self.memory_service = MemoryService()

    def process_memory(
        self,
        db: Session,
        workspace_id: int,
        memory: MemoryCreate,
    ) -> WorkspaceMemory:
        """
        Process a single memory.

        Current behavior:
        - Check for duplicate memory.
        - If duplicate exists, return existing memory.
        - Otherwise create a new memory.
        """

        active_memories = self.memory_service.get_active_memories(
            db=db,
            workspace_id=workspace_id,
        )

        normalized_title = memory.title.strip().lower()

        for existing in active_memories:
            if (
                existing.memory_type == memory.memory_type
                and existing.title.strip().lower() == normalized_title
            ):

                if existing.content.strip() != memory.content.strip():

                    return self.memory_service.update_existing_memory(
                    db=db,
                    db_memory=existing,
                    memory=memory,
                    )

                return self.memory_service.increase_confidence(
                    db=db,
                    db_memory=existing,
                )

        return self.memory_service.create_memory(
            db=db,
            workspace_id=workspace_id,
            memory=memory,
        )

    def process_memories(
        self,
        db: Session,
        workspace_id: int,
        memories: list[dict],
    ) -> list[WorkspaceMemory]:
        """
        Process multiple extracted memories.
        """

        processed_memories: list[WorkspaceMemory] = []

        for memory_data in memories:

            memory = MemoryCreate(
                memory_type=memory_data["memory_type"],
                title=memory_data["title"],
                content=memory_data["content"],
                importance=memory_data.get(
                    "importance",
                    5,
                ),
            )

            processed_memory = self.process_memory(
                db=db,
                workspace_id=workspace_id,
                memory=memory,
            )

            processed_memories.append(
                processed_memory
            )

        return processed_memories