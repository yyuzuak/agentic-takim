"""v0.9.1 tool safety: dry_run/rate_limited/schema_errors kolonları + tool_compensations

Revision ID: 0010_tool_safety
Revises: 0009_tools
Create Date: 2026-06-19
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0010_tool_safety"
down_revision: Union[str, None] = "0009_tools"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("tool_invocations", sa.Column("dry_run", sa.Boolean(), server_default="false", nullable=False))
    op.add_column("tool_invocations", sa.Column("rate_limited", sa.Boolean(), server_default="false", nullable=False))
    op.add_column("tool_invocations", sa.Column("schema_errors", sa.JSON(), nullable=True))

    op.create_table(
        "tool_compensations",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("task_id", sa.String(), nullable=False, index=True),
        sa.Column("node_key", sa.String(), nullable=False),
        sa.Column("tool", sa.String(), nullable=False),
        sa.Column("exec_id", sa.String(), nullable=False),
        sa.Column("compensate_fn", sa.String(), nullable=True),
        sa.Column("compensate_args", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("exec_id", name="uq_tool_compensations_exec_id"),
    )


def downgrade() -> None:
    op.drop_table("tool_compensations")
    for col in ("schema_errors", "rate_limited", "dry_run"):
        op.drop_column("tool_invocations", col)
