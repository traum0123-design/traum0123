"""Add revoked_tokens table

Revision ID: 0010_revoked_tokens
Revises: 0009_monthly_payroll_rows_checks
Create Date: 2025-10-29 00:20:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0010_revoked_tokens"
down_revision = "0009_monthly_payroll_rows_checks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "revoked_tokens",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("typ", sa.String(length=20), nullable=False),
        sa.Column("jti", sa.String(length=64), nullable=False, unique=True),
        sa.Column("exp", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_revoked_typ_jti", "revoked_tokens", ["typ", "jti"])


def downgrade() -> None:
    op.drop_index("ix_revoked_typ_jti", table_name="revoked_tokens")
    op.drop_table("revoked_tokens")

