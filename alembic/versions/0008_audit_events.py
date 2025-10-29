"""Add audit_events table

Revision ID: 0008_audit_events
Revises: 0007_extra_fields_seek_index
Create Date: 2025-10-29 00:00:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0008_audit_events"
down_revision = "0007_extra_fields_seek_index"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "audit_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actor", sa.String(length=120), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=True),
        sa.Column("action", sa.String(length=80), nullable=False),
        sa.Column("resource", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("ip", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("ua", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("result", sa.String(length=40), nullable=False, server_default="ok"),
        sa.Column("meta_json", sa.Text(), nullable=False, server_default=""),
    )
    op.create_index("ix_audit_ts_desc", "audit_events", ["ts"])
    op.create_index("ix_audit_company_ts_desc", "audit_events", ["company_id", "ts"])


def downgrade() -> None:
    op.drop_index("ix_audit_company_ts_desc", table_name="audit_events")
    op.drop_index("ix_audit_ts_desc", table_name="audit_events")
    op.drop_table("audit_events")

