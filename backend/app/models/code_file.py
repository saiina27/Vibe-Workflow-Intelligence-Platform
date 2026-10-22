from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class CodeFile(Base):
    """One source file of a tracked repository (metadata only)."""

    __tablename__ = "code_files"

    __table_args__ = (
        UniqueConstraint("workspace_id", "repo", "path", name="uq_code_file"),
        Index("ix_code_files_ws_repo", "workspace_id", "repo"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    workspace_id: Mapped[int] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )

    repo: Mapped[str] = mapped_column(String(200), nullable=False)
    path: Mapped[str] = mapped_column(String(500), nullable=False)
    sha: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    size: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    indexed_sha: Mapped[str | None] = mapped_column(String(64), nullable=True)
    indexed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error: Mapped[str | None] = mapped_column(String(200), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )


class CodeSymbol(Base):
    """A function, class, method or constant name. No code is stored."""

    __tablename__ = "code_symbols"

    __table_args__ = (
        Index("ix_code_symbols_ws_repo", "workspace_id", "repo"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    file_id: Mapped[int] = mapped_column(
        ForeignKey("code_files.id", ondelete="CASCADE"),
        nullable=False,
    )

    workspace_id: Mapped[int] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )

    repo: Mapped[str] = mapped_column(String(200), nullable=False)
    path: Mapped[str] = mapped_column(String(500), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    qualname: Mapped[str] = mapped_column(String(300), nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    line: Mapped[int] = mapped_column(Integer, nullable=False)
    doc: Mapped[str | None] = mapped_column(String(200), nullable=True)
