"""Add ui_settings table

Revision ID: 0015_ui_settings
Revises: 0014_policy_settings_history
Create Date: 2025-10-29 01:55:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0015_ui_settings"
down_revision = "0014_policy_settings_history"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ui_settings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("key", sa.String(length=120), nullable=False),
        sa.Column("value_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("company_id", "key", name="uq_ui_setting_company_key"),
    )
    op.create_index("ix_ui_settings_company_key", "ui_settings", ["company_id", "key"])


def downgrade() -> None:
    op.drop_index("ix_ui_settings_company_key", table_name="ui_settings")
    op.drop_table("ui_settings")

