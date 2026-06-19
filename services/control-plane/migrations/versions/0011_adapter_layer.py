"""v1.1-a adapter layer: secret_accessed, http_status, compensation applied_result

Revision ID: 0011_adapter_layer
Revises: 0010_tool_safety
Create Date: 2026-06-20
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0011_adapter_layer"
down_revision: Union[str, None] = "0010_tool_safety"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # tool_invocations: secrets audit + http_status
    op.add_column("tool_invocations",
        sa.Column("secret_accessed", sa.Boolean(), server_default="false", nullable=False))
    op.add_column("tool_invocations",
        sa.Column("http_status", sa.Integer(), nullable=True))

    # tool_compensations: apply result + failed status support
    op.add_column("tool_compensations",
        sa.Column("applied_result", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("tool_compensations", "applied_result")
    op.drop_column("tool_invocations", "http_status")
    op.drop_column("tool_invocations", "secret_accessed")
