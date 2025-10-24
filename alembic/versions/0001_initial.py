"""initial schema

Revision ID: 0001_initial
Revises: 
Create Date: 2025-10-24 00:00:00

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0001_initial'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # companies
    op.create_table(
        'companies',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('slug', sa.String(length=80), nullable=False),
        sa.Column('access_hash', sa.String(length=255), nullable=False),
        sa.Column('token_key', sa.String(length=128), nullable=False, server_default=''),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('ix_companies_slug', 'companies', ['slug'], unique=True)

    # monthly_payrolls
    op.create_table(
        'monthly_payrolls',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('company_id', sa.Integer(), nullable=False),
        sa.Column('year', sa.Integer(), nullable=False),
        sa.Column('month', sa.Integer(), nullable=False),
        sa.Column('rows_json', sa.Text(), nullable=False, server_default='[]'),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('is_closed', sa.Boolean(), nullable=False, server_default=sa.text('0')),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id']),
        sa.UniqueConstraint('company_id', 'year', 'month', name='uq_company_month'),
    )
    op.create_index('ix_monthly_payrolls_company_id', 'monthly_payrolls', ['company_id'])

    # extra_fields
    op.create_table(
        'extra_fields',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('company_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('label', sa.String(length=200), nullable=False),
        sa.Column('typ', sa.String(length=20), nullable=False, server_default='number'),
        sa.Column('position', sa.Integer(), nullable=False, server_default='0'),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id']),
        sa.UniqueConstraint('company_id', 'name', name='uq_company_field'),
        sa.UniqueConstraint('company_id', 'label', name='uq_company_field_label'),
    )
    op.create_index('ix_extra_fields_company_id', 'extra_fields', ['company_id'])

    # field_prefs
    op.create_table(
        'field_prefs',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('company_id', sa.Integer(), nullable=False),
        sa.Column('field', sa.String(length=200), nullable=False),
        sa.Column('group', sa.String(length=20), nullable=False, server_default='none'),
        sa.Column('alias', sa.String(length=200), nullable=False, server_default=''),
        sa.Column('exempt_enabled', sa.Boolean(), nullable=False, server_default=sa.text('0')),
        sa.Column('exempt_limit', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('ins_nhis', sa.Boolean(), nullable=False, server_default=sa.text('0')),
        sa.Column('ins_ei', sa.Boolean(), nullable=False, server_default=sa.text('0')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id']),
        sa.UniqueConstraint('company_id', 'field', name='uq_company_fieldpref'),
    )
    op.create_index('ix_field_prefs_company_id', 'field_prefs', ['company_id'])

    # withholding_cells
    op.create_table(
        'withholding_cells',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('year', sa.Integer(), nullable=False),
        sa.Column('dependents', sa.Integer(), nullable=False),
        sa.Column('wage', sa.Integer(), nullable=False),
        sa.Column('tax', sa.Integer(), nullable=False),
        sa.UniqueConstraint('year', 'dependents', 'wage', name='uq_withholding_key'),
    )
    op.create_index('ix_withholding_cells_year', 'withholding_cells', ['year'])
    op.create_index('ix_withholding_cells_dependents', 'withholding_cells', ['dependents'])
    op.create_index('ix_withholding_cells_wage', 'withholding_cells', ['wage'])

    # monthly_payroll_rows
    op.create_table(
        'monthly_payroll_rows',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('payroll_id', sa.Integer(), nullable=False),
        sa.Column('company_id', sa.Integer(), nullable=False),
        sa.Column('employee_code', sa.String(length=80), nullable=True),
        sa.Column('employee_name', sa.String(length=120), nullable=True),
        sa.Column('employee_ssn', sa.String(length=32), nullable=True),
        sa.Column('hire_date', sa.Date(), nullable=True),
        sa.Column('leave_date', sa.Date(), nullable=True),
        sa.Column('leave_start_date', sa.Date(), nullable=True),
        sa.Column('leave_end_date', sa.Date(), nullable=True),
        sa.Column('base_salary', sa.Integer(), nullable=True),
        sa.Column('meal_allowance', sa.Integer(), nullable=True),
        sa.Column('overtime_allowance', sa.Integer(), nullable=True),
        sa.Column('bonus', sa.Integer(), nullable=True),
        sa.Column('extra_allowance', sa.Integer(), nullable=True),
        sa.Column('total_earnings', sa.Integer(), nullable=True),
        sa.Column('national_pension', sa.Integer(), nullable=True),
        sa.Column('health_insurance', sa.Integer(), nullable=True),
        sa.Column('long_term_care', sa.Integer(), nullable=True),
        sa.Column('employment_insurance', sa.Integer(), nullable=True),
        sa.Column('income_tax', sa.Integer(), nullable=True),
        sa.Column('local_income_tax', sa.Integer(), nullable=True),
        sa.Column('employee_insurance_flag', sa.Boolean(), nullable=True),
        sa.Column('other_deductions', sa.Integer(), nullable=True),
        sa.Column('total_deductions', sa.Integer(), nullable=True),
        sa.Column('net_pay', sa.Integer(), nullable=True),
        sa.Column('year', sa.Integer(), nullable=False),
        sa.Column('month', sa.Integer(), nullable=False),
        sa.Column('is_closed', sa.Boolean(), nullable=False, server_default=sa.text('0')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['payroll_id'], ['monthly_payrolls.id']),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id']),
        sa.UniqueConstraint('payroll_id', 'employee_code', name='uq_payroll_row_employee'),
    )
    op.create_index('ix_monthly_payroll_rows_payroll_id', 'monthly_payroll_rows', ['payroll_id'])
    op.create_index('ix_monthly_payroll_rows_company_id', 'monthly_payroll_rows', ['company_id'])


def downgrade() -> None:
    op.drop_index('ix_monthly_payroll_rows_company_id', table_name='monthly_payroll_rows')
    op.drop_index('ix_monthly_payroll_rows_payroll_id', table_name='monthly_payroll_rows')
    op.drop_table('monthly_payroll_rows')

    op.drop_index('ix_withholding_cells_wage', table_name='withholding_cells')
    op.drop_index('ix_withholding_cells_dependents', table_name='withholding_cells')
    op.drop_index('ix_withholding_cells_year', table_name='withholding_cells')
    op.drop_table('withholding_cells')

    op.drop_index('ix_field_prefs_company_id', table_name='field_prefs')
    op.drop_table('field_prefs')

    op.drop_index('ix_extra_fields_company_id', table_name='extra_fields')
    op.drop_table('extra_fields')

    op.drop_index('ix_monthly_payrolls_company_id', table_name='monthly_payrolls')
    op.drop_table('monthly_payrolls')

    op.drop_index('ix_companies_slug', table_name='companies')
    op.drop_table('companies')

