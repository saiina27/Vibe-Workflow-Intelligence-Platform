from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.workspace import Workspace
from app.repositories.workspace_repository import (
    create_workspace,
    get_user_workspaces,
)


def create_new_workspace(
    db: Session,
    user_id: int,
    name: str,
    description: str | None,
):
    workspace = Workspace(
        name=name,
        description=description,
        user_id=user_id,
    )

    return create_workspace(db, workspace)


def list_workspaces(
    db: Session,
    user_id: int,
):
    return get_user_workspaces(
        db,
        user_id,
    )


def require_workspace_access(
    db: Session,
    workspace_id: int,
    user_id: int,
) -> Workspace:
    """
    Verify that the authenticated user owns the workspace.

    This is an application-level authorization boundary.

    The client/LLM cannot override this check.
    """

    workspace = (
        db.query(Workspace)
        .filter(
            Workspace.id == workspace_id,
            Workspace.user_id == user_id,
        )
        .first()
    )

    if workspace is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workspace not found",
        )

    return workspace