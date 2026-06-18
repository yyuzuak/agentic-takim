"""task DAG: tasks.plan + task_nodes

Revision ID: 0003_task_nodes
Revises: 0002_tasks
Create Date: 2026-06-18
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003_task_nodes"
down_revision: Union[str, None] = "0002_tasks"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("tasks", sa.Column("plan", sa.JSON(), nullable=True))
    op.create_table(
        "task_nodes",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("task_id", sa.String(), sa.ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("node_key", sa.String(), nullable=False),
        sa.Column("agent", sa.String(), nullable=False),
        sa.Column("skill", sa.String(), nullable=True),
        sa.Column("depends_on", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("status", sa.String(), nullable=False, server_default="pending"),
        sa.Column("msg_id", sa.String(), nullable=True, index=True),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("task_nodes")
    op.drop_column("tasks", "plan")
