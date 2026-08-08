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