"""Add checks on monthly_payrolls (year, month ranges)

Revision ID: 0011_monthly_payrolls_checks
Revises: 0010_revoked_tokens
Create Date: 2025-10-29 00:28:00.000000
"""
from __future__ import annotations

from alembic import op


revision = "0011_monthly_payrolls_checks"
down_revision = "0010_revoked_tokens"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_check_constraint(
        constraint_name="ck_monthly_payrolls_month_range",
        table_name="monthly_payrolls",
        condition="month >= 1 AND month <= 12",
    )
    op.create_check_constraint(
        constraint_name="ck_monthly_payrolls_year_range",
        table_name="monthly_payrolls",
        condition="year >= 1900 AND year <= 2100",
    )


def downgrade() -> None:
    op.drop_constraint("ck_monthly_payrolls_year_range", "monthly_payrolls", type_="check")
    op.drop_constraint("ck_monthly_payrolls_month_range", "monthly_payrolls", type_="check")

