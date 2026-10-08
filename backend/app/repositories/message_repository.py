from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.chat import Chat
from app.models.message import Message


def create_message(
    db: Session,
    chat_id: int,
    role: str,
    content: str,
):
    message = Message(
        chat_id=chat_id,
        role=role,
        content=content,
    )

    db.add(message)
    db.commit()
    db.refresh(message)

    return message


def get_messages_for_ai(
    db: Session,
    chat_id: int,
):
    return (
        db.query(Message)
        .filter(Message.chat_id == chat_id)
        .order_by(Message.created_at)
        .all()
    )


def _escape_like(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace("%", "\\%")
        .replace("_", "\\_")
    )


def search_messages(
    db: Session,
    workspace_id: int,
    exclude_chat_id: int | None = None,
    keywords: list[str] | None = None,
    start=None,
    end=None,
    limit: int = 6,
):
    """
    Search user/assistant messages of one workspace.

    Always scoped to workspace_id. Returns (Message, Chat) rows,
    newest first.
    """

    query = (
        db.query(Message, Chat)
        .join(Chat, Chat.id == Message.chat_id)
        .filter(Chat.workspace_id == workspace_id)
        .filter(Message.role.in_(["user", "assistant"]))
    )

    if exclude_chat_id is not None:
        query = query.filter(Chat.id != exclude_chat_id)

    if start is not None:
        query = query.filter(Message.created_at >= start)

    if end is not None:
        query = query.filter(Message.created_at < end)

    if keywords:
        query = query.filter(
            or_(
                *[
                    Message.content.ilike(
                        f"%{_escape_like(k)}%",
                        escape="\\",
                    )
                    for k in keywords
                ]
            )
        )

    return (
        query.order_by(Message.created_at.desc())
        .limit(limit)
        .all()
    )
