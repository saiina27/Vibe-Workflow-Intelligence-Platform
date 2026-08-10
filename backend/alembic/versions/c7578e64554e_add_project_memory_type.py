"""add project memory type

Revision ID: c7578e64554e
Revises: 6aef7f97843f
Create Date: 2026-08-09 14:09:59.770231

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c7578e64554e"
down_revision: Union[str, Sequence[str], None] = "6aef7f97843f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    # Add missing enum values
    op.execute(
        "ALTER TYPE memorytype ADD VALUE IF NOT EXISTS 'working';"
    )

    op.execute(
        "ALTER TYPE memorytype ADD VALUE IF NOT EXISTS 'project';"
    )


def downgrade() -> None:
    """Downgrade schema."""

    # PostgreSQL doesn't support removing enum values.
    pass