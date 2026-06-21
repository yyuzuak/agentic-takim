"""v0.8.1 memory consolidation: value_score + last_used_at (dedup/decay/scoring/forgetting)

Revision ID: 0014_memory_consolidation
Revises: 0013_build_runs
Create Date: 2026-06-21
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0014_memory_consolidation"
down_revision: Union[str, None] = "0013_build_runs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("memory_entries",
        sa.Column("value_score", sa.Float(), nullable=False, server_default="1.0"))
    op.add_column("memory_entries",
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("memory_entries", "last_used_at")
    op.drop_column("memory_entries", "value_score")
