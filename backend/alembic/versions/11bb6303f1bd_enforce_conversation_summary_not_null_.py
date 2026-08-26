"""enforce conversation summary not null constraints

Revision ID: 11bb6303f1bd
Revises: a1b923c9bc58
Create Date: 2026-08-26 15:31:09.039040

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "11bb6303f1bd"
down_revision: Union[str, Sequence[str], None] = "a1b923c9bc58"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Enforce NOT NULL constraints on conversation summaries."""

    op.alter_column(
        "conversation_summaries",
        "chat_id",
        existing_type=sa.Integer(),
        nullable=False,
    )

    op.alter_column(
        "conversation_summaries",
        "summary",
        existing_type=sa.Text(),
        nullable=False,
    )

    op.alter_column(
        "conversation_summaries",
        "message_count",
        existing_type=sa.Integer(),
        existing_server_default=sa.text("0"),
        nullable=False,
    )

    op.alter_column(
        "conversation_summaries",
        "created_at",
        existing_type=sa.DateTime(),
        nullable=False,
    )

    op.alter_column(
        "conversation_summaries",
        "updated_at",
        existing_type=sa.DateTime(),
        nullable=False,
    )


def downgrade() -> None:
    """Remove NOT NULL constraints from conversation summaries."""

    op.alter_column(
        "conversation_summaries",
        "updated_at",
        existing_type=sa.DateTime(),
        nullable=True,
    )

    op.alter_column(
        "conversation_summaries",
        "created_at",
        existing_type=sa.DateTime(),
        nullable=True,
    )

    op.alter_column(
        "conversation_summaries",
        "message_count",
        existing_type=sa.Integer(),
        existing_server_default=sa.text("0"),
        nullable=True,
    )

    op.alter_column(
        "conversation_summaries",
        "summary",
        existing_type=sa.Text(),
        nullable=True,
    )

    op.alter_column(
        "conversation_summaries",
        "chat_id",
        existing_type=sa.Integer(),
        nullable=True,
    )