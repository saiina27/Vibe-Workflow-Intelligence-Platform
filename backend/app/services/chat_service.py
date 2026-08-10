from sqlalchemy.orm import Session

from app.models.chat import Chat
from fastapi import HTTPException

from app.repositories.chat_repository import ChatRepository

chat_repository = ChatRepository()

def create_chat(
    db: Session,
    workspace_id: int,
    title: str | None = None,
):
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
):
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
):
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
):
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
):
    return chat_repository.get_by_topic(
        db,
        workspace_id,
        topic,
    )


def get_chats_by_status(
    db: Session,
    workspace_id: int,
    status: str,
):
    return chat_repository.get_by_status(
        db,
        workspace_id,
        status,
    )