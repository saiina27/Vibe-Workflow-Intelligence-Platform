from datetime import datetime
from enum import Enum

from sqlalchemy import (
    DateTime,
    Enum as SQLEnum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.workspace_memory_embedding import WorkspaceMemoryEmbedding


class MemoryType(str, Enum):
    FACT = "fact"
    PREFERENCE = "preference"
    PROFILE = "profile"
    GOAL = "goal"
    DECISION = "decision"
    TASK = "task"
    KNOWLEDGE = "knowledge"
    SUMMARY = "summary"
    WORKING = "working"


class MemorySource(str, Enum):
    USER = "user"
    AI = "ai"
    DOCUMENT = "document"
    TOOL = "tool"
    SYSTEM = "system"


class MemoryStatus(str, Enum):
    ACTIVE = "active"
    ARCHIVED = "archived"
    EXPIRED = "expired"


class WorkspaceMemory(Base):
    __tablename__ = "workspace_memories"

    id: Mapped[int] = mapped_column(
        primary_key=True,
        index=True,
    )

    workspace_id: Mapped[int] = mapped_column(
        ForeignKey("workspaces.id"),
        nullable=False,
    )

    memory_type: Mapped[MemoryType] = mapped_column(
        SQLEnum(
            MemoryType,
            values_callable=lambda enum: [
                e.value for e in enum
            ],
        ),
        nullable=False,
    )
    
    title: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
    )

    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    importance: Mapped[int] = mapped_column(
        Integer,
        default=5,
        nullable=False,
    )

    confidence: Mapped[float] = mapped_column(
        Float,
        default=1.0,
        nullable=False,
    )

    source: Mapped[MemorySource] = mapped_column(
        SQLEnum(
            MemorySource,
            values_callable=lambda enum: [
                e.value for e in enum
            ],
        ),
        default=MemorySource.USER,
        nullable=False,
    )

    status: Mapped[MemoryStatus] = mapped_column(
        SQLEnum(
            MemoryStatus,
            values_callable=lambda enum: [
                e.value for e in enum
            ],
        ),
        default=MemoryStatus.ACTIVE,
        nullable=False,
    )

    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    workspace = relationship(
        "Workspace",
        back_populates="memories",
    )

    embedding: Mapped["WorkspaceMemoryEmbedding | None"] = relationship(
    "WorkspaceMemoryEmbedding",
    back_populates="memory",
    cascade="all, delete-orphan",
    uselist=False,
    )