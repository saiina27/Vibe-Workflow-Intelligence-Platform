"""add tool call logs

Revision ID: a1b923c9bc58
Revises: AUTO_GENERATED
Create Date: 2026-08-25
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "a1b923c9bc58"
down_revision: Union[str, Sequence[str], None] = "6f9b8636ad4f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Register the ToolCallLog schema.

    The table may already exist in databases created during
    Sprint 11 development, so creation is guarded.
    """

    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "tool_call_logs" not in inspector.get_table_names():

        op.create_table(
            "tool_call_logs",

            sa.Column(
                "id",
                sa.Integer(),
                primary_key=True,
                nullable=False,
            ),

            sa.Column(
                "user_id",
                sa.Integer(),
                sa.ForeignKey(
                    "users.id",
                    ondelete="CASCADE",
                ),
                nullable=False,
            ),

            sa.Column(
                "workspace_id",
                sa.Integer(),
                sa.ForeignKey(
                    "workspaces.id",
                    ondelete="CASCADE",
                ),
                nullable=False,
            ),

            sa.Column(
                "tool_call_id",
                sa.String(length=255),
                nullable=False,
            ),

            sa.Column(
                "tool_name",
                sa.String(length=100),
                nullable=False,
            ),

            sa.Column(
                "arguments",
                postgresql.JSONB(
                    astext_type=sa.Text()
                ),
                nullable=False,
            ),

            sa.Column(
                "result",
                postgresql.JSONB(
                    astext_type=sa.Text()
                ),
                nullable=True,
            ),

            sa.Column(
                "status",
                sa.String(length=20),
                nullable=False,
            ),

            sa.Column(
                "error",
                sa.Text(),
                nullable=True,
            ),

            sa.Column(
                "duration_ms",
                sa.Float(),
                nullable=True,
            ),

            sa.Column(
                "created_at",
                sa.DateTime(),
                nullable=False,
            ),
        )

        op.create_index(
            op.f("ix_tool_call_logs_id"),
            "tool_call_logs",
            ["id"],
            unique=False,
        )


def downgrade() -> None:
    """
    Remove ToolCallLog table.
    """

    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "tool_call_logs" in inspector.get_table_names():

        op.drop_index(
            op.f("ix_tool_call_logs_id"),
            table_name="tool_call_logs",
        )

        op.drop_table(
            "tool_call_logs"
        )