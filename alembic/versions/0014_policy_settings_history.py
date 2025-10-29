"""Add policy_settings_history table

Revision ID: 0014_policy_settings_history
Revises: 0013_token_fences
Create Date: 2025-10-29 01:45:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0014_policy_settings_history"
down_revision = "0013_token_fences"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "policy_settings_history",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actor", sa.String(length=120), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=True),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("old_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("new_json", sa.Text(), nullable=False, server_default="{}"),
    )
    op.create_index("ix_policy_hist_company_year_ts", "policy_settings_history", ["company_id", "year", "ts"])


def downgrade() -> None:
    op.drop_index("ix_policy_hist_company_year_ts", table_name="policy_settings_history")
    op.drop_table("policy_settings_history")

