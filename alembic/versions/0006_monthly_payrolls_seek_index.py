"""Add seek-friendly index for monthly_payrolls pagination

Revision ID: 0006_monthly_payrolls_seek_index
Revises: 0005_companies_pagination_idx
Create Date: 2025-10-29

"""
from __future__ import annotations

from alembic import op


# revision identifiers, used by Alembic.
revision = "0006_monthly_payrolls_seek_index"
down_revision = "0005_companies_pagination_idx"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_monthly_payrolls_company_year_month_id",
        "monthly_payrolls",
        ["company_id", "year", "month", "id"],
    )


def downgrade() -> None:
    op.drop_index("ix_monthly_payrolls_company_year_month_id", table_name="monthly_payrolls")

