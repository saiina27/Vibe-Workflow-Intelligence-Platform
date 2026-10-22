"""add code index

Revision ID: e24b6c9d3a15
Revises: d13a0b7e2c41
Create Date: 2026-10-16
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e24b6c9d3a15"
down_revision: Union[str, Sequence[str], None] = "d13a0b7e2c41"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    tables = inspector.get_table_names()

    if "code_files" not in tables:
        op.create_table(
            "code_files",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column(
                "workspace_id",
                sa.Integer(),
                sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("repo", sa.String(length=200), nullable=False),
            sa.Column("path", sa.String(length=500), nullable=False),
            sa.Column("sha", sa.String(length=64), nullable=False),
            sa.Column("size", sa.Integer(), nullable=False),
            sa.Column("indexed_sha", sa.String(length=64), nullable=True),
            sa.Column("indexed_at", sa.DateTime(), nullable=True),
            sa.Column("attempts", sa.Integer(), nullable=False),
            sa.Column("error", sa.String(length=200), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint(
                "workspace_id", "repo", "path", name="uq_code_file"
            ),
        )
        op.create_index(
            op.f("ix_code_files_id"), "code_files", ["id"], unique=False
        )
        op.create_index(
            "ix_code_files_ws_repo",
            "code_files",
            ["workspace_id", "repo"],
            unique=False,
        )

    if "code_symbols" not in tables:
        op.create_table(
            "code_symbols",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column(
                "file_id",
                sa.Integer(),
                sa.ForeignKey("code_files.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "workspace_id",
                sa.Integer(),
                sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("repo", sa.String(length=200), nullable=False),
            sa.Column("path", sa.String(length=500), nullable=False),
            sa.Column("name", sa.String(length=200), nullable=False),
            sa.Column("qualname", sa.String(length=300), nullable=False),
            sa.Column("kind", sa.String(length=20), nullable=False),
            sa.Column("line", sa.Integer(), nullable=False),
            sa.Column("doc", sa.String(length=200), nullable=True),
        )
        op.create_index(
            op.f("ix_code_symbols_id"), "code_symbols", ["id"], unique=False
        )
        op.create_index(
            "ix_code_symbols_ws_repo",
            "code_symbols",
            ["workspace_id", "repo"],
            unique=False,
        )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    tables = inspector.get_table_names()

    if "code_symbols" in tables:
        op.drop_index("ix_code_symbols_ws_repo", table_name="code_symbols")
        op.drop_index(op.f("ix_code_symbols_id"), table_name="code_symbols")
        op.drop_table("code_symbols")

    if "code_files" in tables:
        op.drop_index("ix_code_files_ws_repo", table_name="code_files")
        op.drop_index(op.f("ix_code_files_id"), table_name="code_files")
        op.drop_table("code_files")
