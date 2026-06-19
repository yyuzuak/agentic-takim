"""v0.8 memory-aware planning: memory_entries

Revision ID: 0008_memory
Revises: 0007_refinement
Create Date: 2026-06-19
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0008_memory"
down_revision: Union[str, None] = "0007_refinement"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "memory_entries",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("task_id", sa.String(), nullable=False),
        sa.Column("goal", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("outcome", sa.String(), nullable=False, server_default="done"),
        sa.Column("plan", sa.JSON(), nullable=True),
        sa.Column("tags", sa.JSON(), nullable=True),
        sa.Column("memory_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("workflow_type", sa.String(), nullable=True),
        sa.Column("planner_source", sa.String(), nullable=True),
        sa.Column("success_score", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("refinement_summary", sa.JSON(), nullable=True),
        sa.Column("retrieval_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("reuse_success_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(), nullable=False, server_default="pending"),
        sa.Column("provider", sa.String(), nullable=True),
        sa.Column("parent_memory_ids", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("task_id", name="uq_memory_entries_task_id"),
    )
    op.create_index("ix_memory_entries_task_id", "memory_entries", ["task_id"])


def downgrade() -> None:
    op.drop_index("ix_memory_entries_task_id", table_name="memory_entries")
    op.drop_table("memory_entries")
