"""HITL: tasks approval alanları + task_plan_versions

Revision ID: 0004_hitl
Revises: 0003_task_nodes
Create Date: 2026-06-18
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004_hitl"
down_revision: Union[str, None] = "0003_task_nodes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("tasks", sa.Column("require_approval", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("tasks", sa.Column("current_plan_version", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("tasks", sa.Column("last_modified_by", sa.String(), nullable=True))
    op.add_column("tasks", sa.Column("approval_deadline", sa.DateTime(timezone=True), nullable=True))
    op.create_table(
        "task_plan_versions",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("task_id", sa.String(), sa.ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("plan_json", sa.JSON(), nullable=False),
        sa.Column("created_by", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("task_plan_versions")
    op.drop_column("tasks", "approval_deadline")
    op.drop_column("tasks", "last_modified_by")
    op.drop_column("tasks", "current_plan_version")
    op.drop_column("tasks", "require_approval")
