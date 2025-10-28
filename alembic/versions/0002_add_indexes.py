"""Add composite indexes for performance

Revision ID: 0002_add_indexes
Revises: 0001_initial
Create Date: 2025-10-28

"""
from __future__ import annotations

from alembic import op


# revision identifiers, used by Alembic.
revision = "0002_add_indexes"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_withholding_year_dep_wage",
        "withholding_cells",
        ["year", "dependents", "wage"],
    )
    op.create_index(
        "ix_company_year_month",
        "monthly_payrolls",
        ["company_id", "year", "month"],
    )


def downgrade() -> None:
    op.drop_index("ix_company_year_month", table_name="monthly_payrolls")
    op.drop_index("ix_withholding_year_dep_wage", table_name="withholding_cells")

