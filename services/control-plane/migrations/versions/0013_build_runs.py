"""v2.2 build execution: build_runs tablosu (sandbox çalıştırma sonuçları + structured errors)

Revision ID: 0013_build_runs
Revises: 0012_builds
Create Date: 2026-06-21
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0013_build_runs"
down_revision: Union[str, None] = "0012_builds"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "build_runs",
        sa.Column("run_id", sa.String(), primary_key=True),
        sa.Column("build_id", sa.String(), nullable=False, index=True),
        sa.Column("status", sa.String(), nullable=False),  # passed | failed
        sa.Column("stage", sa.String(), nullable=False),   # install|prisma|build|done|setup
        sa.Column("install_ok", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("prisma_ok", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("build_ok", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("duration_s", sa.Float(), nullable=False, server_default="0"),
        sa.Column("errors", sa.JSON(), nullable=True),
        sa.Column("log_tail", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("build_runs")
