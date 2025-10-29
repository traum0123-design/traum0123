"""Add policy_settings table

Revision ID: 0012_policy_settings
Revises: 0011_monthly_payrolls_checks
Create Date: 2025-10-29 00:35:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0012_policy_settings"
down_revision = "0011_monthly_payrolls_checks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "policy_settings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), nullable=True),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("policy_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("company_id", "year", name="uq_policy_company_year"),
    )
    op.create_index("ix_policy_company_year", "policy_settings", ["company_id", "year"])


def downgrade() -> None:
    op.drop_index("ix_policy_company_year", table_name="policy_settings")
    op.drop_table("policy_settings")

