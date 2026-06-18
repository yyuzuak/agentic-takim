"""init registry tables (agents, skills, agent_skills)

Revision ID: 0001_init_registry
Revises:
Create Date: 2026-06-18
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001_init_registry"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "agents",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("display_name", sa.String(), nullable=False),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("type", sa.String(), nullable=False, server_default="agent"),
    )
    op.create_table(
        "skills",
        sa.Column("id", sa.String(), primary_key=True),
    )
    op.create_table(
        "agent_skills",
        sa.Column("agent_id", sa.String(), sa.ForeignKey("agents.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("skill_id", sa.String(), sa.ForeignKey("skills.id", ondelete="CASCADE"), primary_key=True),
    )


def downgrade() -> None:
    op.drop_table("agent_skills")
    op.drop_table("skills")
    op.drop_table("agents")
