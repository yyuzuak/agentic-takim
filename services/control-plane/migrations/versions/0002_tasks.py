"""tasks table (ACP görev yaşam döngüsü)

Revision ID: 0002_tasks
Revises: 0001_init_registry
Create Date: 2026-06-18
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002_tasks"
down_revision: Union[str, None] = "0001_init_registry"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tasks",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("trace_id", sa.String(), nullable=False, index=True),
        sa.Column("agent", sa.String(), nullable=False),
        sa.Column("skill", sa.String(), nullable=True),
        sa.Column("goal", sa.Text(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="pending"),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    # index=True kolon üzerinde otomatik ix_tasks_trace_id oluşturur; tekrar create_index YOK.


def downgrade() -> None:
    op.drop_table("tasks")
