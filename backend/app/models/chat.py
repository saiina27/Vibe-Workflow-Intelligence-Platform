from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Chat(Base):
    __tablename__ = "chats"

    id: Mapped[int] = mapped_column(
        primary_key=True,
        index=True,
    )

    title: Mapped[str] = mapped_column(
        String(200),
    )

    workspace_id: Mapped[int] = mapped_column(
        ForeignKey("workspaces.id"),
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
    )

    workspace = relationship(
        "Workspace",
        back_populates="chats",
    )

    messages = relationship(
    "Message",
    back_populates="chat",
    cascade="all, delete",
    )

    summary = relationship(
    "ConversationSummary",
    back_populates="chat",
    uselist=False,
    cascade="all, delete"
    )