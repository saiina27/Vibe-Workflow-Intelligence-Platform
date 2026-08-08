from sqlalchemy.orm import Session

from app.models.chat import Chat


def create_chat(
    db: Session,
    workspace_id: int,
    title: str,
):
    chat = Chat(
        title=title,
        workspace_id=workspace_id,
    )

    db.add(chat)
    db.commit()
    db.refresh(chat)

    return chat


def get_workspace_chats(
    db: Session,
    workspace_id: int,
):
    return (
        db.query(Chat)
        .filter(Chat.workspace_id == workspace_id)
        .order_by(Chat.created_at.desc())
        .all()
    )