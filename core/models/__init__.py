from __future__ import annotations

import datetime as dt
from typing import Optional

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, Index
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


class Company(Base):
    __tablename__ = "companies"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(80), nullable=False, unique=True, index=True)
    access_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    token_key: Mapped[str] = mapped_column(String(128), default="")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    payrolls: Mapped[list["MonthlyPayroll"]] = relationship(back_populates="company", cascade="all, delete-orphan")
    # Optional backref for business income records
    bizincomes: Mapped[list["MonthlyBizIncome"]] = relationship(back_populates="company", cascade="all, delete-orphan")


class MonthlyPayroll(Base):
    __tablename__ = "monthly_payrolls"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), nullable=False, index=True)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    month: Mapped[int] = mapped_column(Integer, nullable=False)
    rows_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)
    is_closed: Mapped[bool] = mapped_column(Boolean, default=False)

    company: Mapped[Company] = relationship(back_populates="payrolls")

    __table_args__ = (
        UniqueConstraint("company_id", "year", "month", name="uq_company_month"),
        Index("ix_company_year_month", "company_id", "year", "month"),
    )


class MonthlyBizIncome(Base):
    __tablename__ = "monthly_bizincome"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), nullable=False, index=True)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    month: Mapped[int] = mapped_column(Integer, nullable=False)
    rows_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)
    is_closed: Mapped[bool] = mapped_column(Boolean, default=False)

    company: Mapped[Company] = relationship(back_populates="bizincomes")

    __table_args__ = (
        UniqueConstraint("company_id", "year", "month", name="uq_bizincome_company_month"),
        Index("ix_bizincome_company_year_month", "company_id", "year", "month"),
    )

class MonthlyBizIncomeRow(Base):
    __tablename__ = "bizincome_rows"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    bizincome_id: Mapped[int] = mapped_column(ForeignKey("monthly_bizincome.id"), nullable=False, index=True)
    company_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), default="")
    pid: Mapped[str] = mapped_column(String(128), default="")  # encrypted or masked
    resident_type: Mapped[str] = mapped_column(String(20), default="")  # 내국인/외국인
    biz_type: Mapped[str] = mapped_column(String(40), default="")      # 예: 기타자영업
    amount: Mapped[int | None] = mapped_column(Integer)
    rate: Mapped[int | None] = mapped_column(Integer)
    tax: Mapped[int | None] = mapped_column(Integer)
    local_tax: Mapped[int | None] = mapped_column(Integer)
    total_tax: Mapped[int | None] = mapped_column(Integer)
    net_amount: Mapped[int | None] = mapped_column(Integer)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    month: Mapped[int] = mapped_column(Integer, nullable=False)
    is_closed: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    __table_args__ = (
        Index("ix_bizincome_row_company_year_month", "company_id", "year", "month"),
    )


class ExtraField(Base):
    __tablename__ = "extra_fields"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)  # internal key (한글 허용)
    label: Mapped[str] = mapped_column(String(200), nullable=False)
    typ: Mapped[str] = mapped_column(String(20), default="number")
    position: Mapped[int] = mapped_column(Integer, default=0)

    __table_args__ = (
        UniqueConstraint("company_id", "name", name="uq_company_field"),
        UniqueConstraint("company_id", "label", name="uq_company_field_label"),
    )


class FieldPref(Base):
    __tablename__ = "field_prefs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), nullable=False, index=True)
    field: Mapped[str] = mapped_column(String(200), nullable=False)
    group: Mapped[str] = mapped_column(String(20), default="none")  # earn/deduct/none
    alias: Mapped[str] = mapped_column(String(200), default="")
    # Optional per-field flags
    exempt_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    exempt_limit: Mapped[int] = mapped_column(Integer, default=0)
    ins_nhis: Mapped[bool] = mapped_column(Boolean, default=False)
    ins_ei: Mapped[bool] = mapped_column(Boolean, default=False)
    # Whether this earning field should be prorated (일할계산 적용)
    prorate: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    __table_args__ = (
        UniqueConstraint("company_id", "field", name="uq_company_fieldpref"),
    )


class WithholdingCell(Base):
    __tablename__ = "withholding_cells"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    year: Mapped[int] = mapped_column(Integer, index=True)
    dependents: Mapped[int] = mapped_column(Integer, index=True)
    wage: Mapped[int] = mapped_column(Integer, index=True)  # 월 급여액(과세표준 월보수)
    tax: Mapped[int] = mapped_column(Integer)  # 소득세 금액(원)

    __table_args__ = (
        UniqueConstraint("year", "dependents", "wage", name="uq_withholding_key"),
        Index("ix_withholding_year_dep_wage", "year", "dependents", "wage"),
    )


class MonthlyPayrollRow(Base):
    __tablename__ = "monthly_payroll_rows"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    payroll_id: Mapped[int] = mapped_column(ForeignKey("monthly_payrolls.id"), nullable=False, index=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), nullable=False, index=True)
    employee_code: Mapped[str | None] = mapped_column(String(80))
    employee_name: Mapped[str | None] = mapped_column(String(120))
    employee_ssn: Mapped[str | None] = mapped_column(String(32))
    hire_date: Mapped[dt.date | None] = mapped_column(Date)
    leave_date: Mapped[dt.date | None] = mapped_column(Date)
    leave_start_date: Mapped[dt.date | None] = mapped_column(Date)
    leave_end_date: Mapped[dt.date | None] = mapped_column(Date)
    base_salary: Mapped[int | None] = mapped_column(Integer)
    meal_allowance: Mapped[int | None] = mapped_column(Integer)
    overtime_allowance: Mapped[int | None] = mapped_column(Integer)
    bonus: Mapped[int | None] = mapped_column(Integer)
    extra_allowance: Mapped[int | None] = mapped_column(Integer)
    total_earnings: Mapped[int | None] = mapped_column(Integer)
    national_pension: Mapped[int | None] = mapped_column(Integer)
    health_insurance: Mapped[int | None] = mapped_column(Integer)
    long_term_care: Mapped[int | None] = mapped_column(Integer)
    employment_insurance: Mapped[int | None] = mapped_column(Integer)
    income_tax: Mapped[int | None] = mapped_column(Integer)
    local_income_tax: Mapped[int | None] = mapped_column(Integer)
    employee_insurance_flag: Mapped[bool | None] = mapped_column(Boolean)
    other_deductions: Mapped[int | None] = mapped_column(Integer)
    total_deductions: Mapped[int | None] = mapped_column(Integer)
    net_pay: Mapped[int | None] = mapped_column(Integer)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    month: Mapped[int] = mapped_column(Integer, nullable=False)
    is_closed: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    payroll: Mapped[MonthlyPayroll] = relationship("MonthlyPayroll", backref="rows_normalized")
    company: Mapped[Company] = relationship("Company")

    __table_args__ = (
        UniqueConstraint("payroll_id", "employee_code", name="uq_payroll_row_employee"),
    )


class IdempotencyRecord(Base):
    __tablename__ = "idempotency_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(128), nullable=False)
    method: Mapped[str] = mapped_column(String(10), nullable=False)
    path: Mapped[str] = mapped_column(String(255), nullable=False)
    body_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    company_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status_code: Mapped[int] = mapped_column(Integer, default=200)
    response_json: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    __table_args__ = (
        UniqueConstraint("key", "method", "path", name="uq_idem_key_method_path"),
        Index("ix_idem_created_at", "created_at"),
    )


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ts: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)
    actor: Mapped[str] = mapped_column(String(120))  # e.g., "admin" or "company:acme"
    company_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(80))  # e.g., "login_success", "export_download"
    resource: Mapped[str] = mapped_column(String(255), default="")  # e.g., path or logical resource
    ip: Mapped[str] = mapped_column(String(64), default="")
    ua: Mapped[str] = mapped_column(String(255), default="")
    result: Mapped[str] = mapped_column(String(40), default="ok")  # ok/fail/denied
    meta_json: Mapped[str] = mapped_column(Text, default="")

    __table_args__ = (
        Index("ix_audit_ts_desc", "ts"),
        Index("ix_audit_company_ts_desc", "company_id", "ts"),
    )


class RevokedToken(Base):
    __tablename__ = "revoked_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    typ: Mapped[str] = mapped_column(String(20), nullable=False)  # e.g., 'admin'
    jti: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    exp: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    __table_args__ = (
        Index("ix_revoked_typ_jti", "typ", "jti"),
    )


class PolicySetting(Base):
    __tablename__ = "policy_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    year: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    policy_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    __table_args__ = (
        UniqueConstraint("company_id", "year", name="uq_policy_company_year"),
        Index("ix_policy_company_year", "company_id", "year"),
    )


class PolicySettingHistory(Base):
    __tablename__ = "policy_settings_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ts: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)
    actor: Mapped[str] = mapped_column(String(120))  # e.g., 'admin'
    company_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    year: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    old_json: Mapped[str] = mapped_column(Text, default="{}")
    new_json: Mapped[str] = mapped_column(Text, default="{}")

    __table_args__ = (
        Index("ix_policy_hist_company_year_ts", "company_id", "year", "ts"),
    )


class UISetting(Base):
    __tablename__ = "ui_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    key: Mapped[str] = mapped_column(String(120), nullable=False)
    value_json: Mapped[str] = mapped_column(Text, default="{}")
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    __table_args__ = (
        UniqueConstraint("company_id", "key", name="uq_ui_setting_company_key"),
        Index("ix_ui_settings_company_key", "company_id", "key"),
    )


class TokenFence(Base):
    __tablename__ = "token_fences"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    typ: Mapped[str] = mapped_column(String(20), nullable=False)
    revoked_before_iat: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    __table_args__ = (
        UniqueConstraint("typ", name="uq_token_fence_typ"),
    )
