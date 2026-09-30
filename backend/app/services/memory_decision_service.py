from sqlalchemy.orm import Session

from app.ai.embedding_service import EmbeddingService
from app.models.workspace_memory import WorkspaceMemory
from app.repositories.embedding_repository import (
    EmbeddingRepository,
)
from app.schemas.workspace_memory import MemoryCreate
from app.services.memory_service import MemoryService


# Cosine similarity above this is treated as the same
# underlying fact, even if the extracted title wording
# differs (e.g. "Find Repository" vs "Find Repository
# Vibe-Workflow-Intelligence-Platform").
DUPLICATE_SIMILARITY_THRESHOLD = 0.90


class MemoryDecisionService:

    def __init__(self):
        self.memory_service = MemoryService()
        self.embedding_service = EmbeddingService()
        self.embedding_repository = EmbeddingRepository()

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

        # ----------------------------------------------------
        # SEMANTIC DUPLICATE CHECK
        #
        # Title wording can vary between extractions even when
        # the underlying fact is the same. Fall back to
        # embedding similarity within the same memory_type
        # before creating a new row. Any failure here (e.g. the
        # embedding API is unavailable) degrades to the old
        # behavior of creating a new memory, rather than raising.
        # ----------------------------------------------------

        try:

            query_embedding = (
                self.embedding_service.generate_embedding(
                    memory.content
                )
            )

            matches = (
                self.embedding_repository.find_similar_in_type(
                    db=db,
                    workspace_id=workspace_id,
                    memory_type=memory.memory_type,
                    query_embedding=query_embedding,
                    limit=1,
                )
            )

        except Exception as exc:

            print(
                f"Memory similarity check failed: {exc}"
            )

            matches = []

        if matches:

            closest, distance = matches[0]
            similarity = 1 - distance

            if similarity >= DUPLICATE_SIMILARITY_THRESHOLD:

                if closest.content.strip() != memory.content.strip():

                    return self.memory_service.update_existing_memory(
                        db=db,
                        db_memory=closest,
                        memory=memory,
                    )

                return self.memory_service.increase_confidence(
                    db=db,
                    db_memory=closest,
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