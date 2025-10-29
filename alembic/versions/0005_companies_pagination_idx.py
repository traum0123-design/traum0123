"""Add composite index for companies pagination

Revision ID: 0005_companies_pagination_idx
Revises: 0004_idempotency_records
Create Date: 2025-10-29

"""
from __future__ import annotations

from alembic import op


# revision identifiers, used by Alembic.
revision = "0005_companies_pagination_idx"
down_revision = "0004_idempotency_records"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Composite index to support order by created_at, id
    op.create_index("ix_companies_created_id", "companies", ["created_at", "id"]) 


def downgrade() -> None:
    op.drop_index("ix_companies_created_id", table_name="companies")

