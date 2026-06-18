"""v0.7 multi-agent collaboration: event-sourced context + projections + node_role

Revision ID: 0006_collaboration
Revises: 0005_retry_failure
Create Date: 2026-06-18
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0006_collaboration"
down_revision: Union[str, None] = "0005_retry_failure"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("task_nodes", sa.Column("node_role", sa.String(), nullable=False, server_default="producer"))

    op.create_table(
        "task_context_events",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("task_id", sa.String(), nullable=False, index=True),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("type", sa.String(), nullable=False),
        sa.Column("agent", sa.String(), nullable=True),
        sa.Column("node_key", sa.String(), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("exec_id", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "task_context_snapshot",
        sa.Column("task_id", sa.String(), primary_key=True),
        sa.Column("snapshot", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "task_artifacts",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("task_id", sa.String(), nullable=False, index=True),
        sa.Column("node_key", sa.String(), nullable=False),
        sa.Column("agent", sa.String(), nullable=True),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("content", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "task_critiques",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("task_id", sa.String(), nullable=False, index=True),
        sa.Column("target_node", sa.String(), nullable=True),
        sa.Column("critic_agent", sa.String(), nullable=True),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("issues", sa.JSON(), nullable=True),
        sa.Column("suggestions", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("task_critiques")
    op.drop_table("task_artifacts")
    op.drop_table("task_context_snapshot")
    op.drop_table("task_context_events")
    op.drop_column("task_nodes", "node_role")
