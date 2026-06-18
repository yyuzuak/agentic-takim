"""v0.6 retry & failure: TaskNode retry alanları + tasks.inputs + dead_letter_nodes + processed_executions

Revision ID: 0005_retry_failure
Revises: 0004_hitl
Create Date: 2026-06-18
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005_retry_failure"
down_revision: Union[str, None] = "0004_hitl"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("tasks", sa.Column("inputs", sa.JSON(), nullable=True))

    op.add_column("task_nodes", sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("task_nodes", sa.Column("max_retries", sa.Integer(), nullable=False, server_default="3"))
    op.add_column("task_nodes", sa.Column("retry_policy", sa.String(), nullable=False, server_default="exponential"))
    op.add_column("task_nodes", sa.Column("last_error", sa.Text(), nullable=True))
    op.add_column("task_nodes", sa.Column("error_code", sa.String(), nullable=True))
    op.add_column("task_nodes", sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("task_nodes", sa.Column("retry_at", sa.DateTime(timezone=True), nullable=True, index=True))
    op.add_column("task_nodes", sa.Column("exec_id", sa.String(), nullable=True))
    op.add_column("task_nodes", sa.Column("retry_history", sa.JSON(), nullable=True))

    op.create_table(
        "dead_letter_nodes",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("task_id", sa.String(), nullable=False, index=True),
        sa.Column("node_id", sa.String(), nullable=False, index=True),
        sa.Column("node_key", sa.String(), nullable=False),
        sa.Column("error_code", sa.String(), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("retry_history", sa.JSON(), nullable=True),
        sa.Column("dag_context_hash", sa.String(), nullable=True),
        sa.Column("dependency_snapshot", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "processed_executions",
        sa.Column("exec_id", sa.String(), primary_key=True),
        sa.Column("processed_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("processed_executions")
    op.drop_table("dead_letter_nodes")
    for col in ("retry_history", "exec_id", "retry_at", "failed_at", "error_code",
                "last_error", "retry_policy", "max_retries", "retry_count"):
        op.drop_column("task_nodes", col)
    op.drop_column("tasks", "inputs")
