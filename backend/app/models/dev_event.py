from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class DevEvent(Base):
    """
    One normalized development event (commit, pull request, ...).

    Only metadata is stored: no code, no diffs, no emails.
    """

    __tablename__ = "dev_events"

    __table_args__ = (
        UniqueConstraint(
            "workspace_id", "source", "repo", "external_id",
            name="uq_dev_event_external",
        ),
        Index("ix_dev_events_ws_time", "workspace_id", "occurred_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    workspace_id: Mapped[int] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )

    source: Mapped[str] = mapped_column(String(20), nullable=False)
    repo: Mapped[str] = mapped_column(String(200), nullable=False)
    event_type: Mapped[str] = mapped_column(String(30), nullable=False)
    external_id: Mapped[str] = mapped_column(String(100), nullable=False)

    title: Mapped[str] = mapped_column(String(500), nullable=False)
    author: Mapped[str | None] = mapped_column(String(200), nullable=True)
    url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    detail: Mapped[str | None] = mapped_column(String(100), nullable=True)

    occurred_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
