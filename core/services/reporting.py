from __future__ import annotations

from typing import Dict

from sqlalchemy import func
from sqlalchemy.orm import Session

from core.models import MonthlyPayrollRow


def monthly_summary(
    session: Session,
    company_id: int,
    year: int,
    month: int,
) -> Dict[str, int]:
    row = (
        session.query(
            func.coalesce(func.sum(MonthlyPayrollRow.base_salary), 0),
            func.coalesce(func.sum(MonthlyPayrollRow.meal_allowance), 0),
            func.coalesce(func.sum(MonthlyPayrollRow.overtime_allowance), 0),
            func.coalesce(func.sum(MonthlyPayrollRow.bonus), 0),
            func.coalesce(func.sum(MonthlyPayrollRow.extra_allowance), 0),
            func.coalesce(func.sum(MonthlyPayrollRow.total_earnings), 0),
            func.coalesce(func.sum(MonthlyPayrollRow.national_pension), 0),
            func.coalesce(func.sum(MonthlyPayrollRow.health_insurance), 0),
            func.coalesce(func.sum(MonthlyPayrollRow.long_term_care), 0),
            func.coalesce(func.sum(MonthlyPayrollRow.employment_insurance), 0),
            func.coalesce(func.sum(MonthlyPayrollRow.income_tax), 0),
            func.coalesce(func.sum(MonthlyPayrollRow.local_income_tax), 0),
            func.coalesce(func.sum(MonthlyPayrollRow.other_deductions), 0),
            func.coalesce(func.sum(MonthlyPayrollRow.total_deductions), 0),
            func.coalesce(func.sum(MonthlyPayrollRow.net_pay), 0),
        )
        .filter(
            MonthlyPayrollRow.company_id == company_id,
            MonthlyPayrollRow.year == year,
            MonthlyPayrollRow.month == month,
        )
        .first()
    )

    if not row:
        return {
            "base_salary": 0,
            "meal_allowance": 0,
            "overtime_allowance": 0,
            "bonus": 0,
            "extra_allowance": 0,
            "total_earnings": 0,
            "national_pension": 0,
            "health_insurance": 0,
            "long_term_care": 0,
            "employment_insurance": 0,
            "income_tax": 0,
            "local_income_tax": 0,
            "other_deductions": 0,
            "total_deductions": 0,
            "net_pay": 0,
        }

    (
        base_salary,
        meal_allowance,
        overtime_allowance,
        bonus,
        extra_allowance,
        total_earnings,
        national_pension,
        health_insurance,
        long_term_care,
        employment_insurance,
        income_tax,
        local_income_tax,
        other_deductions,
        total_deductions,
        net_pay,
    ) = row

    return {
        "base_salary": int(base_salary),
        "meal_allowance": int(meal_allowance),
        "overtime_allowance": int(overtime_allowance),
        "bonus": int(bonus),
        "extra_allowance": int(extra_allowance),
        "total_earnings": int(total_earnings),
        "national_pension": int(national_pension),
        "health_insurance": int(health_insurance),
        "long_term_care": int(long_term_care),
        "employment_insurance": int(employment_insurance),
        "income_tax": int(income_tax),
        "local_income_tax": int(local_income_tax),
        "other_deductions": int(other_deductions),
        "total_deductions": int(total_deductions),
        "net_pay": int(net_pay),
    }
