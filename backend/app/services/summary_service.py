from sqlalchemy.orm import Session

from app.models.conversation_summary import ConversationSummary
from app.repositories.conversation_summary_repository import (
    conversation_summary_repository,
)


class SummaryService:

    def get_summary(
        self,
        db: Session,
        chat_id: int,
    ) -> ConversationSummary | None:
        return conversation_summary_repository.get_by_chat_id(
            db=db,
            chat_id=chat_id,
        )

    def should_generate_summary(
        self,
        message_count: int,
        last_summary_count: int | None,
    ) -> bool:

        if last_summary_count is None:
            return message_count >= 5

        return (message_count - last_summary_count) >= 5

    def save_summary(
        self,
        db: Session,
        chat_id: int,
        summary: str,
        message_count: int,
    ) -> ConversationSummary:

        existing_summary = self.get_summary(
            db=db,
            chat_id=chat_id,
        )

        if existing_summary is None:
            return conversation_summary_repository.create(
                db=db,
                chat_id=chat_id,
                summary=summary,
                message_count=message_count,
            )

        return conversation_summary_repository.update(
            db=db,
            conversation_summary=existing_summary,
            summary=summary,
            message_count=message_count,
        )


summary_service = SummaryService()