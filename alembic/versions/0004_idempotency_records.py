"""Add idempotency_records table

Revision ID: 0004_idempotency_records
Revises: 0003_add_prorate_flag
Create Date: 2025-10-29

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0004_idempotency_records"
down_revision = "0003_add_prorate_flag"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "idempotency_records",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("key", sa.String(length=128), nullable=False),
        sa.Column("method", sa.String(length=10), nullable=False),
        sa.Column("path", sa.String(length=255), nullable=False),
        sa.Column("body_hash", sa.String(length=64), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=True),
        sa.Column("status_code", sa.Integer(), nullable=False, server_default="200"),
        sa.Column("response_json", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("key", "method", "path", name="uq_idem_key_method_path"),
    )
    op.create_index("ix_idem_created_at", "idempotency_records", ["created_at"]) 


def downgrade() -> None:
    op.drop_index("ix_idem_created_at", table_name="idempotency_records")
    op.drop_table("idempotency_records")

