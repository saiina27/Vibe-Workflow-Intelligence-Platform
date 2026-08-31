from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.chat import Chat
from app.repositories.chat_repository import ChatRepository
from app.services.workspace_service import require_workspace_access


chat_repository = ChatRepository()


def create_chat(
    db: Session,
    workspace_id: int,
    title: str | None = None,
    user_id: int | None = None,
):
    if user_id is not None:
        require_workspace_access(
            db=db,
            workspace_id=workspace_id,
            user_id=user_id,
        )

    chat = Chat(
        title=title or "New Chat",
        workspace_id=workspace_id,
    )

    db.add(chat)
    db.commit()
    db.refresh(chat)

    return chat


def get_workspace_chats(
    db: Session,
    workspace_id: int,
    user_id: int,
):
    require_workspace_access(
        db=db,
        workspace_id=workspace_id,
        user_id=user_id,
    )

    return (
        db.query(Chat)
        .filter(Chat.workspace_id == workspace_id)
        .order_by(Chat.created_at.desc())
        .all()
    )


def archive_chat(
    db: Session,
    workspace_id: int,
    chat_id: int,
    user_id: int,
):
    require_workspace_access(
        db=db,
        workspace_id=workspace_id,
        user_id=user_id,
    )

    chat = chat_repository.get_by_id(
        db,
        chat_id,
    )

    if (
        chat is None
        or chat.workspace_id != workspace_id
    ):
        raise HTTPException(
            status_code=404,
            detail="Chat not found",
        )

    return chat_repository.archive(
        db,
        chat,
    )


def restore_chat(
    db: Session,
    workspace_id: int,
    chat_id: int,
    user_id: int,
):
    require_workspace_access(
        db=db,
        workspace_id=workspace_id,
        user_id=user_id,
    )

    chat = chat_repository.get_by_id(
        db,
        chat_id,
    )

    if (
        chat is None
        or chat.workspace_id != workspace_id
    ):
        raise HTTPException(
            status_code=404,
            detail="Chat not found",
        )

    return chat_repository.restore(
        db,
        chat,
    )


def get_chats_by_topic(
    db: Session,
    workspace_id: int,
    topic: str,
    user_id: int,
):
    require_workspace_access(
        db=db,
        workspace_id=workspace_id,
        user_id=user_id,
    )

    return chat_repository.get_by_topic(
        db,
        workspace_id,
        topic,
    )


def get_chats_by_status(
    db: Session,
    workspace_id: int,
    status: str,
    user_id: int,
):
    require_workspace_access(
        db=db,
        workspace_id=workspace_id,
        user_id=user_id,
    )

    return chat_repository.get_by_status(
        db,
        workspace_id,
        status,
    )