from __future__ import annotations

import datetime as dt
from typing import Optional

from sqlalchemy import Integer, Numeric, String, ForeignKey, UniqueConstraint, Boolean, Date, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship

from payroll_shared.models import Base, Company, MonthlyPayroll, utc_now


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
