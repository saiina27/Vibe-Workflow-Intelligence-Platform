from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.chat import Chat

class ChatRepository:

    def get_by_id(
        self,
        db: Session,
        chat_id: int,
    ) -> Chat | None:

        statement = (
            select(Chat)
            .where(Chat.id == chat_id)
        )

        return db.scalar(statement)

    def update_title(
        self,
        db: Session,
        chat: Chat,
        title: str,
    ) -> Chat:

        chat.title = title

        db.commit()
        db.refresh(chat)

        return chat

    def update_status(
        self,
        db: Session,
        chat: Chat,
        status: str,
    ) -> Chat:

        chat.status = status

        db.commit()
        db.refresh(chat)

        return chat

    def archive(
        self,
        db: Session,
        chat: Chat,
    ) -> Chat:

        return self.update_status(
            db,
            chat,
            "archived",
        )

    def restore(
        self,
        db: Session,
        chat: Chat,
    ) -> Chat:

        return self.update_status(
            db,
            chat,
            "active",
        )

    def get_by_topic(
        self,
        db: Session,
        workspace_id: int,
        topic: str,
    ):

        statement = (
            select(Chat)
            .where(Chat.workspace_id == workspace_id)
            .where(Chat.topic == topic)
            .order_by(Chat.updated_at.desc())
        )

        return list(db.scalars(statement))

    def get_by_status(
        self,
        db: Session,
        workspace_id: int,
        status: str,
    ):

        statement = (
            select(Chat)
            .where(Chat.workspace_id == workspace_id)
            .where(Chat.status == status)
            .order_by(Chat.updated_at.desc())
        )

        return list(db.scalars(statement))