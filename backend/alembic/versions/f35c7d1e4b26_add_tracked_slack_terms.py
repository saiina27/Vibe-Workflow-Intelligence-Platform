"""add tracked slack terms

Revision ID: f35c7d1e4b26
Revises: e24b6c9d3a15
Create Date: 2026-11-09
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f35c7d1e4b26"
down_revision: Union[str, Sequence[str], None] = "e24b6c9d3a15"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())

    if "tracked_slack_terms" not in inspector.get_table_names():
        op.create_table(
            "tracked_slack_terms",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column(
                "workspace_id",
                sa.Integer(),
                sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("term", sa.String(length=60), nullable=False),
            sa.Column("last_synced_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint("workspace_id", "term", name="uq_slack_term"),
        )
        op.create_index(
            op.f("ix_tracked_slack_terms_id"),
            "tracked_slack_terms",
            ["id"],
            unique=False,
        )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())

    if "tracked_slack_terms" in inspector.get_table_names():
        op.drop_index(
            op.f("ix_tracked_slack_terms_id"), table_name="tracked_slack_terms"
        )
        op.drop_table("tracked_slack_terms")
