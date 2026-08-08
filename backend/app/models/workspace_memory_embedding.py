from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class WorkspaceMemoryEmbedding(Base):
    __tablename__ = "workspace_memory_embeddings"

    id: Mapped[int] = mapped_column(
        primary_key=True,
        index=True,
    )

    memory_id: Mapped[int] = mapped_column(
        ForeignKey(
            "workspace_memories.id",
            ondelete="CASCADE",
        ),
        unique=True,
        nullable=False,
    )

    embedding: Mapped[list[float]] = mapped_column(
        Vector(768),
        nullable=False,
    )

    model: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    dimension: Mapped[int] = mapped_column(
        Integer,
        default=768,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )

    memory = relationship(
        "WorkspaceMemory",
        back_populates="embedding",
    )