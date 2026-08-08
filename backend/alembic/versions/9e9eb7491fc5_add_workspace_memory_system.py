"""add workspace memory system

Revision ID: 9e9eb7491fc5
Revises: f117b6c88ac2
Create Date: 2026-08-07 18:27:27.845418

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from pgvector.sqlalchemy import Vector


# revision identifiers, used by Alembic.
revision: str = "9e9eb7491fc5"
down_revision: Union[str, Sequence[str], None] = "f117b6c88ac2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the complete workspace memory system."""

    # ---------------------------------------------------------
    # 1. Create memory enums
    # ---------------------------------------------------------

    memory_type_enum = postgresql.ENUM(
        "fact",
        "preference",
        "profile",
        "goal",
        "decision",
        "task",
        "knowledge",
        "summary",
        "working",
        name="memorytype",
        create_type=False,
    )

    memory_source_enum = postgresql.ENUM(
        "user",
        "ai",
        "document",
        "tool",
        "system",
        name="memorysource",
        create_type=False,
    )

    memory_status_enum = postgresql.ENUM(
        "active",
        "archived",
        "expired",
        name="memorystatus",
        create_type=False,
    )

    # PostgreSQL ENUMs must be created explicitly.
    op.execute(
        """
        CREATE TYPE memorytype AS ENUM (
            'fact',
            'preference',
            'profile',
            'goal',
            'decision',
            'task',
            'knowledge',
            'summary',
            'working'
        )
        """
    )

    op.execute(
        """
        CREATE TYPE memorysource AS ENUM (
            'user',
            'ai',
            'document',
            'tool',
            'system'
        )
        """
    )

    op.execute(
        """
        CREATE TYPE memorystatus AS ENUM (
            'active',
            'archived',
            'expired'
        )
        """
    )

    # ---------------------------------------------------------
    # 2. Create workspace_memories
    # ---------------------------------------------------------

    op.create_table(
        "workspace_memories",

        sa.Column(
            "id",
            sa.Integer(),
            nullable=False,
        ),

        sa.Column(
            "workspace_id",
            sa.Integer(),
            nullable=False,
        ),

        sa.Column(
            "memory_type",
            memory_type_enum,
            nullable=False,
        ),

        sa.Column(
            "title",
            sa.String(length=200),
            nullable=False,
        ),

        sa.Column(
            "content",
            sa.Text(),
            nullable=False,
        ),

        sa.Column(
            "importance",
            sa.Integer(),
            nullable=False,
            server_default="5",
        ),

        sa.Column(
            "confidence",
            sa.Float(),
            nullable=False,
            server_default="1.0",
        ),

        sa.Column(
            "source",
            memory_source_enum,
            nullable=False,
            server_default="user",
        ),

        sa.Column(
            "status",
            memory_status_enum,
            nullable=False,
            server_default="active",
        ),

        sa.Column(
            "expires_at",
            sa.DateTime(),
            nullable=True,
        ),

        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
        ),

        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
        ),

        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
        ),

        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        "ix_workspace_memories_id",
        "workspace_memories",
        ["id"],
        unique=False,
    )

    # ---------------------------------------------------------
    # 3. Create workspace_memory_embeddings
    # ---------------------------------------------------------

    op.create_table(
        "workspace_memory_embeddings",

        sa.Column(
            "id",
            sa.Integer(),
            nullable=False,
        ),

        sa.Column(
            "memory_id",
            sa.Integer(),
            nullable=False,
        ),

        sa.Column(
            "embedding",
            Vector(768),
            nullable=False,
        ),

        sa.Column(
            "model",
            sa.String(length=100),
            nullable=False,
        ),

        sa.Column(
            "dimension",
            sa.Integer(),
            nullable=False,
            server_default="768",
        ),

        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
        ),

        sa.ForeignKeyConstraint(
            ["memory_id"],
            ["workspace_memories.id"],
            ondelete="CASCADE",
        ),

        sa.PrimaryKeyConstraint("id"),

        sa.UniqueConstraint("memory_id"),
    )

    op.create_index(
        "ix_workspace_memory_embeddings_id",
        "workspace_memory_embeddings",
        ["id"],
        unique=False,
    )

    # ---------------------------------------------------------
    # 4. Create conversation_summaries
    # ---------------------------------------------------------

    op.create_table(
        "conversation_summaries",

        sa.Column(
            "id",
            sa.Integer(),
            nullable=False,
        ),

        sa.Column(
            "chat_id",
            sa.Integer(),
            nullable=True,
        ),

        sa.Column(
            "summary",
            sa.Text(),
            nullable=True,
        ),

        sa.Column(
            "message_count",
            sa.Integer(),
            nullable=True,
            server_default="0",
        ),

        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=True,
        ),

        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=True,
        ),

        sa.ForeignKeyConstraint(
            ["chat_id"],
            ["chats.id"],
        ),

        sa.PrimaryKeyConstraint("id"),

        sa.UniqueConstraint("chat_id"),
    )

    op.create_index(
        "ix_conversation_summaries_id",
        "conversation_summaries",
        ["id"],
        unique=False,
    )


def downgrade() -> None:
    """Drop the complete workspace memory system."""

    op.drop_index(
        "ix_conversation_summaries_id",
        table_name="conversation_summaries",
    )

    op.drop_table("conversation_summaries")

    op.drop_index(
        "ix_workspace_memory_embeddings_id",
        table_name="workspace_memory_embeddings",
    )

    op.drop_table("workspace_memory_embeddings")

    op.drop_index(
        "ix_workspace_memories_id",
        table_name="workspace_memories",
    )

    op.drop_table("workspace_memories")

    op.execute("DROP TYPE IF EXISTS memorystatus")
    op.execute("DROP TYPE IF EXISTS memorysource")
    op.execute("DROP TYPE IF EXISTS memorytype")