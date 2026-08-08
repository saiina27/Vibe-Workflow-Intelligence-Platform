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