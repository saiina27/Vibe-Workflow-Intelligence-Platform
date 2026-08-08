from sqlalchemy.orm import Session

from app.models.conversation_summary import ConversationSummary


class ConversationSummaryRepository:

    def get_by_chat_id(
        self,
        db: Session,
        chat_id: int,
    ) -> ConversationSummary | None:
        return (
            db.query(ConversationSummary)
            .filter(ConversationSummary.chat_id == chat_id)
            .first()
        )

    def create(
        self,
        db: Session,
        *,
        chat_id: int,
        summary: str,
        message_count: int,
    ) -> ConversationSummary:

        conversation_summary = ConversationSummary(
            chat_id=chat_id,
            summary=summary,
            message_count=message_count,
        )

        db.add(conversation_summary)
        db.commit()
        db.refresh(conversation_summary)

        return conversation_summary

    def update(
        self,
        db: Session,
        conversation_summary: ConversationSummary,
        *,
        summary: str,
        message_count: int,
    ) -> ConversationSummary:

        conversation_summary.summary = summary
        conversation_summary.message_count = message_count

        db.commit()
        db.refresh(conversation_summary)

        return conversation_summary


conversation_summary_repository = ConversationSummaryRepository()