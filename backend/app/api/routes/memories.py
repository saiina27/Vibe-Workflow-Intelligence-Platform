from fastapi import APIRouter, Depends, HTTPException, status, Response
from sqlalchemy.orm import Session

from app.dependencies.database import get_db
from app.schemas.workspace_memory import (
    MemoryCreate,
    MemoryUpdate,
    MemoryResponse,
)
from app.services.memory_service import MemoryService

router = APIRouter(
    prefix="/workspaces/{workspace_id}/memories",
    tags=["Workspace Memories"],
)

memory_service = MemoryService()


@router.post(
    "",
    response_model=MemoryResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_memory(
    workspace_id: int,
    memory: MemoryCreate,
    db: Session = Depends(get_db),
):
    return memory_service.create_memory(
        db=db,
        workspace_id=workspace_id,
        memory=memory,
    )


@router.get(
    "",
    response_model=list[MemoryResponse],
)
def get_workspace_memories(
    workspace_id: int,
    db: Session = Depends(get_db),
):
    return memory_service.get_workspace_memories(
        db=db,
        workspace_id=workspace_id,
    )


@router.patch(
    "/{memory_id}",
    response_model=MemoryResponse,
)
def update_memory(
    workspace_id: int,
    memory_id: int,
    memory: MemoryUpdate,
    db: Session = Depends(get_db),
):
    updated_memory = memory_service.update_memory(
        db=db,
        memory_id=memory_id,
        memory=memory,
    )

    if updated_memory is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Memory not found",
        )

    return updated_memory


@router.delete(
    "/{memory_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_memory(
    workspace_id: int,
    memory_id: int,
    db: Session = Depends(get_db),
):

    deleted = memory_service.delete_memory(
        db=db,
        memory_id=memory_id,
    )

    if not deleted:
        raise HTTPException(
            status_code=404,
            detail="Memory not found",
        )

    return Response(status_code=status.HTTP_204_NO_CONTENT)