"""v0.7.1 refinement loop: task_nodes.refine_depth + refine_group

Revision ID: 0007_refinement
Revises: 0006_collaboration
Create Date: 2026-06-19
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0007_refinement"
down_revision: Union[str, None] = "0006_collaboration"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("task_nodes", sa.Column("refine_depth", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("task_nodes", sa.Column("refine_group", sa.String(), nullable=True))
    op.create_index("ix_task_nodes_refine_group", "task_nodes", ["refine_group"])


def downgrade() -> None:
    op.drop_index("ix_task_nodes_refine_group", table_name="task_nodes")
    op.drop_column("task_nodes", "refine_group")
    op.drop_column("task_nodes", "refine_depth")
