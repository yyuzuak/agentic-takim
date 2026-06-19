"""v0.9 tool execution: task_nodes tool alanları + tool_invocations

Revision ID: 0009_tools
Revises: 0008_memory
Create Date: 2026-06-19
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0009_tools"
down_revision: Union[str, None] = "0008_memory"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("task_nodes", sa.Column("node_kind", sa.String(), nullable=False, server_default="reasoning"))
    op.add_column("task_nodes", sa.Column("tool", sa.String(), nullable=True))
    op.add_column("task_nodes", sa.Column("tool_args", sa.JSON(), nullable=True))
    op.add_column("task_nodes", sa.Column("approved_by", sa.String(), nullable=True))
    op.add_column("task_nodes", sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True))

    op.create_table(
        "tool_invocations",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("task_id", sa.String(), nullable=False, index=True),
        sa.Column("node_key", sa.String(), nullable=False),
        sa.Column("tool", sa.String(), nullable=False),
        sa.Column("args", sa.JSON(), nullable=True),
        sa.Column("exec_id", sa.String(), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(), nullable=False, server_default="requested"),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("error_code", sa.String(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("exec_id", name="uq_tool_invocations_exec_id"),
    )
    # index=True kolonlar (task_id, exec_id) otomatik index oluşturur; tekrar create_index YOK.


def downgrade() -> None:
    op.drop_table("tool_invocations")
    for col in ("approved_at", "approved_by", "tool_args", "tool", "node_kind"):
        op.drop_column("task_nodes", col)
