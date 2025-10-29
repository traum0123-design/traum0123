from __future__ import annotations

import datetime as dt
from typing import Dict, List

from sqlalchemy.orm import Session

from core.models import MonthlyPayroll, MonthlyPayrollRow
from core.utils.pii import encrypt_ssn, mask_ssn
from core.utils.dates import parse_date_flex


def sync_normalized_rows(
    session: Session,
    payroll: MonthlyPayroll,
    rows: List[Dict],
) -> None:
    session.query(MonthlyPayrollRow).filter(MonthlyPayrollRow.payroll_id == payroll.id).delete()
    for row in rows:
        session.add(_build_row(payroll, row))


def _build_row(payroll: MonthlyPayroll, row: Dict) -> MonthlyPayrollRow:
    hire_date = _to_date(row.get("입사일"))
    leave_date = _to_date(row.get("퇴사일"))
    leave_start = _to_date(row.get("휴직일"))
    leave_end = _to_date(row.get("휴직종료일"))
    insurance_flag = _to_bool(row.get("4대보험가입") or row.get("보험가입"))

    return MonthlyPayrollRow(
        payroll_id=payroll.id,
        company_id=payroll.company_id,
        employee_code=_to_str(row.get("사원코드")),
        employee_name=_to_str(row.get("사원명")),
        employee_ssn=_store_ssn(_to_str(row.get("주민등록번호"))),
        hire_date=hire_date,
        leave_date=leave_date,
        leave_start_date=leave_start,
        leave_end_date=leave_end,
        base_salary=_to_int(row.get("기본급")),
        meal_allowance=_to_int(row.get("식대")),
        overtime_allowance=_to_int(row.get("연장근로수당")),
        bonus=_to_int(row.get("상여")),
        extra_allowance=_to_int(row.get("기타수당")),
        total_earnings=_to_int(row.get("총지급")),
        national_pension=_to_int(row.get("국민연금")),
        health_insurance=_to_int(row.get("건강보험")),
        long_term_care=_to_int(row.get("장기요양보험")),
        employment_insurance=_to_int(row.get("고용보험")),
        income_tax=_to_int(row.get("소득세")),
        local_income_tax=_to_int(row.get("지방소득세")),
        other_deductions=_to_int(row.get("기타공제")),
        total_deductions=_to_int(row.get("총공제")),
        net_pay=_to_int(row.get("실지급")),
        employee_insurance_flag=insurance_flag,
        year=payroll.year,
        month=payroll.month,
        is_closed=bool(getattr(payroll, "is_closed", False)),
    )


def _to_str(value) -> str:
    return str(value or "").strip()


def _store_ssn(ssn: str) -> str:
    """Encrypt SSN when possible; otherwise store masked."""
    s = (ssn or "").strip()
    if not s:
        return ""
    enc = encrypt_ssn(s)
    # encrypt_ssn falls back to mask when crypto/KEY unavailable
    return enc if enc.startswith("enc:") else mask_ssn(s)


def _to_int(value) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(str(value).replace(",", ""))
    except Exception:
        return None


def _to_bool(value) -> bool | None:
    if value in (None, ""):
        return None
    s = str(value).strip().lower()
    if s in {"1", "y", "yes", "true", "on", "t", "가입"}:
        return True
    if s in {"0", "n", "no", "false", "off", "f"}:
        return False
    return None


def _to_date(value) -> dt.date | None:
    return parse_date_flex(value)
