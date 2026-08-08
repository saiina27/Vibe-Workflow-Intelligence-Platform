from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.dependencies.database import get_db
from app.schemas.workspace import (
    WorkspaceCreate,
    WorkspaceResponse,
)
from app.services.auth_service import get_current_user
from app.services.workspace_service import (
    create_new_workspace,
    list_workspaces,
)

router = APIRouter(
    prefix="/workspaces",
    tags=["Workspaces"],
)


@router.post(
    "/",
    response_model=WorkspaceResponse,
)
def create_workspace(
    request: WorkspaceCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    return create_new_workspace(
        db=db,
        user_id=current_user.id,
        name=request.name,
        description=request.description,
    )


@router.get(
    "/",
    response_model=list[WorkspaceResponse],
)
def get_workspaces(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    return list_workspaces(
        db=db,
        user_id=current_user.id,
    )