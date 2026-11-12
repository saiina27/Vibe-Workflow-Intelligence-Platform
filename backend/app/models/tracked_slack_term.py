from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class TrackedSlackTerm(Base):
    """A word the user wants Vibe to look for in Slack (search is by word)."""

    __tablename__ = "tracked_slack_terms"

    __table_args__ = (
        UniqueConstraint("workspace_id", "term", name="uq_slack_term"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    workspace_id: Mapped[int] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )

    term: Mapped[str] = mapped_column(String(60), nullable=False)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
