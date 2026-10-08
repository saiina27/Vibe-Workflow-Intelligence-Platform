"""add tracked repos and dev events

Revision ID: d13a0b7e2c41
Revises: cb770f43d26f
Create Date: 2026-10-08
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d13a0b7e2c41"
down_revision: Union[str, Sequence[str], None] = "cb770f43d26f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    tables = inspector.get_table_names()

    if "tracked_repos" not in tables:
        op.create_table(
            "tracked_repos",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column(
                "workspace_id",
                sa.Integer(),
                sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("full_name", sa.String(length=200), nullable=False),
            sa.Column("last_synced_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint(
                "workspace_id", "full_name", name="uq_tracked_repo"
            ),
        )
        op.create_index(
            op.f("ix_tracked_repos_id"), "tracked_repos", ["id"], unique=False
        )

    if "dev_events" not in tables:
        op.create_table(
            "dev_events",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column(
                "workspace_id",
                sa.Integer(),
                sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("source", sa.String(length=20), nullable=False),
            sa.Column("repo", sa.String(length=200), nullable=False),
            sa.Column("event_type", sa.String(length=30), nullable=False),
            sa.Column("external_id", sa.String(length=100), nullable=False),
            sa.Column("title", sa.String(length=500), nullable=False),
            sa.Column("author", sa.String(length=200), nullable=True),
            sa.Column("url", sa.String(length=500), nullable=True),
            sa.Column("detail", sa.String(length=100), nullable=True),
            sa.Column("occurred_at", sa.DateTime(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint(
                "workspace_id", "source", "repo", "external_id",
                name="uq_dev_event_external",
            ),
        )
        op.create_index(
            op.f("ix_dev_events_id"), "dev_events", ["id"], unique=False
        )
        op.create_index(
            "ix_dev_events_ws_time",
            "dev_events",
            ["workspace_id", "occurred_at"],
            unique=False,
        )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    tables = inspector.get_table_names()

    if "dev_events" in tables:
        op.drop_index("ix_dev_events_ws_time", table_name="dev_events")
        op.drop_index(op.f("ix_dev_events_id"), table_name="dev_events")
        op.drop_table("dev_events")

    if "tracked_repos" in tables:
        op.drop_index(op.f("ix_tracked_repos_id"), table_name="tracked_repos")
        op.drop_table("tracked_repos")
