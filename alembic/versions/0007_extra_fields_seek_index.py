"""Add seek-friendly index for extra_fields pagination

Revision ID: 0007_extra_fields_seek_index
Revises: 0006_monthly_payrolls_seek_index
Create Date: 2025-10-29

"""
from __future__ import annotations

from alembic import op


# revision identifiers, used by Alembic.
revision = "0007_extra_fields_seek_index"
down_revision = "0006_monthly_payrolls_seek_index"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_extra_fields_company_position_id",
        "extra_fields",
        ["company_id", "position", "id"],
    )


def downgrade() -> None:
    op.drop_index("ix_extra_fields_company_position_id", table_name="extra_fields")

