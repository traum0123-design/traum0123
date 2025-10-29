"""Add non-negative checks to monthly_payroll_rows numeric columns

Revision ID: 0009_monthly_payroll_rows_checks
Revises: 0008_audit_events
Create Date: 2025-10-29 00:10:00.000000
"""
from __future__ import annotations

from alembic import op


revision = "0009_monthly_payroll_rows_checks"
down_revision = "0008_audit_events"
branch_labels = None
depends_on = None


def upgrade() -> None:
    cols = [
        "base_salary",
        "meal_allowance",
        "overtime_allowance",
        "bonus",
        "extra_allowance",
        "total_earnings",
        "national_pension",
        "health_insurance",
        "long_term_care",
        "employment_insurance",
        "income_tax",
        "local_income_tax",
        "other_deductions",
        "total_deductions",
        "net_pay",
    ]
    for c in cols:
        op.create_check_constraint(
            constraint_name=f"ck_mpr_{c}_nonneg",
            table_name="monthly_payroll_rows",
            condition=f"({c} IS NULL) OR ({c} >= 0)",
        )


def downgrade() -> None:
    cols = [
        "base_salary",
        "meal_allowance",
        "overtime_allowance",
        "bonus",
        "extra_allowance",
        "total_earnings",
        "national_pension",
        "health_insurance",
        "long_term_care",
        "employment_insurance",
        "income_tax",
        "local_income_tax",
        "other_deductions",
        "total_deductions",
        "net_pay",
    ]
    for c in cols:
        op.drop_constraint(f"ck_mpr_{c}_nonneg", "monthly_payroll_rows", type_="check")

