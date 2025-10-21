from __future__ import annotations

import datetime as dt
from typing import List, Optional

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


class Company(Base):
    __tablename__ = "companies"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(80), nullable=False, unique=True, index=True)
    access_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    token_key: Mapped[str] = mapped_column(String(128), default="")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    payrolls: Mapped[List["MonthlyPayroll"]] = relationship(back_populates="company", cascade="all, delete-orphan")


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
    )


class MonthlyPayrollRow(Base):
    __tablename__ = "monthly_payroll_rows"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    payroll_id: Mapped[int] = mapped_column(ForeignKey("monthly_payrolls.id"), nullable=False, index=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), nullable=False, index=True)
    employee_code: Mapped[Optional[str]] = mapped_column(String(80))
    employee_name: Mapped[Optional[str]] = mapped_column(String(120))
    employee_ssn: Mapped[Optional[str]] = mapped_column(String(32))
    hire_date: Mapped[Optional[dt.date]] = mapped_column(Date)
    leave_date: Mapped[Optional[dt.date]] = mapped_column(Date)
    leave_start_date: Mapped[Optional[dt.date]] = mapped_column(Date)
    leave_end_date: Mapped[Optional[dt.date]] = mapped_column(Date)
    base_salary: Mapped[Optional[int]] = mapped_column(Integer)
    meal_allowance: Mapped[Optional[int]] = mapped_column(Integer)
    overtime_allowance: Mapped[Optional[int]] = mapped_column(Integer)
    bonus: Mapped[Optional[int]] = mapped_column(Integer)
    extra_allowance: Mapped[Optional[int]] = mapped_column(Integer)
    total_earnings: Mapped[Optional[int]] = mapped_column(Integer)
    national_pension: Mapped[Optional[int]] = mapped_column(Integer)
    health_insurance: Mapped[Optional[int]] = mapped_column(Integer)
    long_term_care: Mapped[Optional[int]] = mapped_column(Integer)
    employment_insurance: Mapped[Optional[int]] = mapped_column(Integer)
    income_tax: Mapped[Optional[int]] = mapped_column(Integer)
    local_income_tax: Mapped[Optional[int]] = mapped_column(Integer)
    employee_insurance_flag: Mapped[Optional[bool]] = mapped_column(Boolean)
    other_deductions: Mapped[Optional[int]] = mapped_column(Integer)
    total_deductions: Mapped[Optional[int]] = mapped_column(Integer)
    net_pay: Mapped[Optional[int]] = mapped_column(Integer)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    month: Mapped[int] = mapped_column(Integer, nullable=False)
    is_closed: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    payroll: Mapped[MonthlyPayroll] = relationship("MonthlyPayroll", backref="rows_normalized")
    company: Mapped[Company] = relationship("Company")

    __table_args__ = (
        UniqueConstraint("payroll_id", "employee_code", name="uq_payroll_row_employee"),
    )
