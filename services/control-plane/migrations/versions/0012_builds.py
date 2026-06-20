"""v2.1 workspace runtime: builds tablosu (build kayıtları + DAG snapshot + validator versioning)

Revision ID: 0012_builds
Revises: 0011_adapter_layer
Create Date: 2026-06-20
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0012_builds"
down_revision: Union[str, None] = "0011_adapter_layer"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "builds",
        sa.Column("build_id", sa.String(), primary_key=True),
        sa.Column("build_fingerprint", sa.String(), nullable=False, index=True),
        sa.Column("task_id", sa.String(), nullable=False, index=True),
        sa.Column("build_number", sa.Integer(), nullable=False, default=1),
        sa.Column("stack", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),  # validated | failed
        sa.Column("dag_snapshot", sa.JSON(), nullable=True),
        sa.Column("assembler_version", sa.String(), nullable=False),
        sa.Column("validator_version", sa.String(), nullable=False),
        sa.Column("validator_result", sa.JSON(), nullable=True),
        sa.Column("file_count", sa.Integer(), nullable=False, default=0),
        sa.Column("workspace_path", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("builds")
