"""add monthly_bizincome table

Revision ID: 0016_monthly_bizincome
Revises: 0015_ui_settings
Create Date: 2025-11-10

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0016_monthly_bizincome'
down_revision = '0015_ui_settings'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'monthly_bizincome',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('company_id', sa.Integer(), sa.ForeignKey('companies.id'), nullable=False, index=True),
        sa.Column('year', sa.Integer(), nullable=False),
        sa.Column('month', sa.Integer(), nullable=False),
        sa.Column('rows_json', sa.Text(), nullable=False, server_default='[]'),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('is_closed', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.UniqueConstraint('company_id', 'year', 'month', name='uq_bizincome_company_month'),
    )
    op.create_index('ix_bizincome_company_year_month', 'monthly_bizincome', ['company_id', 'year', 'month'])


def downgrade() -> None:
    op.drop_index('ix_bizincome_company_year_month', table_name='monthly_bizincome')
    op.drop_constraint('uq_bizincome_company_month', 'monthly_bizincome', type_='unique')
    op.drop_table('monthly_bizincome')
