"""add chat intelligence metadata

Revision ID: 6aef7f97843f
Revises: 9e9eb7491fc5
Create Date: 2026-08-08 22:37:34.897745

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "6aef7f97843f"
down_revision: Union[str, Sequence[str], None] = "9e9eb7491fc5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    op.add_column(
        "chats",
        sa.Column(
            "topic",
            sa.String(length=200),
            nullable=True,
        ),
    )

    op.add_column(
        "chats",
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=True,
        ),
    )

    op.add_column(
        "chats",
        sa.Column(
            "message_count",
            sa.Integer(),
            nullable=True,
        ),
    )

    op.add_column(
        "chats",
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=True,
        ),
    )

    op.add_column(
        "chats",
        sa.Column(
            "last_message_at",
            sa.DateTime(),
            nullable=True,
        ),
    )

    # Backfill existing chats.
    op.execute(
        "UPDATE chats SET status = 'active' WHERE status IS NULL"
    )

    op.execute(
        "UPDATE chats SET message_count = 0 "
        "WHERE message_count IS NULL"
    )

    op.execute(
        "UPDATE chats SET updated_at = created_at "
        "WHERE updated_at IS NULL"
    )

    # Enforce constraints after backfilling existing rows.
    op.alter_column(
        "chats",
        "status",
        existing_type=sa.String(length=20),
        nullable=False,
    )

    op.alter_column(
        "chats",
        "message_count",
        existing_type=sa.Integer(),
        nullable=False,
    )

    op.alter_column(
        "chats",
        "updated_at",
        existing_type=sa.DateTime(),
        nullable=False,
    )


def downgrade() -> None:
    """Downgrade schema."""

    op.drop_column("chats", "last_message_at")
    op.drop_column("chats", "updated_at")
    op.drop_column("chats", "message_count")
    op.drop_column("chats", "status")
    op.drop_column("chats", "topic")