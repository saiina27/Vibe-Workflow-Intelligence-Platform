from sqlalchemy.orm import Session

from app.models.workspace import Workspace


def create_workspace(
    db: Session,
    workspace: Workspace,
):
    db.add(workspace)
    db.commit()
    db.refresh(workspace)
    return workspace


def get_user_workspaces(
    db: Session,
    user_id: int,
):
    return (
        db.query(Workspace)
        .filter(Workspace.user_id == user_id)
        .all()
    )

def update_workspace(
    db: Session,
    workspace: Workspace,
):
    db.commit()
    db.refresh(workspace)
    return workspace
