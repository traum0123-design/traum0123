"""Add prorate flag to field_prefs

Revision ID: 0003_add_prorate_flag
Revises: 0002_add_indexes
Create Date: 2025-10-28

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0003_add_prorate_flag"
down_revision = "0002_add_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("field_prefs", sa.Column("prorate", sa.Boolean(), nullable=False, server_default=sa.false()))
    # Remove server_default to keep model default behavior
    with op.batch_alter_table("field_prefs") as batch_op:
        batch_op.alter_column("prorate", server_default=None)


def downgrade() -> None:
    with op.batch_alter_table("field_prefs") as batch_op:
        batch_op.drop_column("prorate")

