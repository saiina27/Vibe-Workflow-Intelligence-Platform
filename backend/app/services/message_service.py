from sqlalchemy.orm import Session

from app.models.message import Message


def create_user_message(
    db: Session,
    chat_id: int,
    content: str,
):
    message = Message(
        chat_id=chat_id,
        role="user",
        content=content,
    )

    db.add(message)
    db.commit()
    db.refresh(message)

    return message


def get_chat_messages(
    db: Session,
    chat_id: int,
):
    return (
        db.query(Message)
        .filter(Message.chat_id == chat_id)
        .order_by(Message.created_at)
        .all()
    )

def create_assistant_message(
    db: Session,
    chat_id: int,
    content: str,
):
    message = Message(
        chat_id=chat_id,
        role="assistant",
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