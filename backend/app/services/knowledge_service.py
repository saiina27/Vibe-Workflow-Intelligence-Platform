from sqlalchemy.orm import Session

from app.models.knowledge_source import (
    KnowledgeSource,
    KnowledgeStatus,
)
from app.repositories.knowledge_repository import (
    KnowledgeRepository,
)


class KnowledgeService:

    def __init__(self):
        self.repository = KnowledgeRepository()

    def create_source(
        self,
        db: Session,
        source: KnowledgeSource,
    ) -> KnowledgeSource:

        return self.repository.create_source(
            db=db,
            source=source,
        )

    def get_source(
        self,
        db: Session,
        source_id: int,
        workspace_id: int | None = None,
    ) -> KnowledgeSource | None:

        source = self.repository.get_by_id(
            db=db,
            source_id=source_id,
        )

        if source is None:
            return None

        if (
            workspace_id is not None
            and source.workspace_id != workspace_id
        ):
            return None

        return source

    def get_workspace_sources(
        self,
        db: Session,
        workspace_id: int,
    ) -> list[KnowledgeSource]:

        return self.repository.get_workspace_sources(
            db=db,
            workspace_id=workspace_id,
        )

    def update_status(
        self,
        db: Session,
        source: KnowledgeSource,
        status: KnowledgeStatus,
        workspace_id: int | None = None,
    ) -> KnowledgeSource | None:

        if (
            workspace_id is not None
            and source.workspace_id != workspace_id
        ):
            return None

        return self.repository.update_status(
            db=db,
            source=source,
            status=status,
        )

    def save_chunks(
        self,
        db: Session,
        chunks,
    ) -> None:

        self.repository.create_chunks(
            db=db,
            chunks=chunks,
        )

    def delete_source(
        self,
        db: Session,
        source_id: int,
        workspace_id: int,
    ) -> bool:

        source = self.repository.get_by_id(
            db=db,
            source_id=source_id,
        )

        if source is None:
            return False

        # Defense-in-depth:
        # a source from another workspace cannot be deleted.
        if source.workspace_id != workspace_id:
            return False

        self.repository.delete(
            db=db,
            source=source,
        )

        return True