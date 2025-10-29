"""Add token_fences table

Revision ID: 0013_token_fences
Revises: 0012_policy_settings
Create Date: 2025-10-29 01:10:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0013_token_fences"
down_revision = "0012_policy_settings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "token_fences",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("typ", sa.String(length=20), nullable=False),
        sa.Column("revoked_before_iat", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("typ", name="uq_token_fence_typ"),
    )


def downgrade() -> None:
    op.drop_table("token_fences")

