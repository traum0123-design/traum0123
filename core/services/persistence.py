from __future__ import annotations

import datetime as dt
from typing import Dict, List

from sqlalchemy.orm import Session

from core.models import MonthlyPayroll, MonthlyPayrollRow, MonthlyBizIncome, MonthlyBizIncomeRow
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


# ---------------- Business Income (사업소득) ----------------
def sync_bizincome_rows(
    session: Session,
    record: MonthlyBizIncome,
    rows: List[Dict],
) -> None:
    session.query(MonthlyBizIncomeRow).filter(MonthlyBizIncomeRow.bizincome_id == record.id).delete()
    for row in rows or []:
        session.add(_build_bizincome_row(record, row))


def _build_bizincome_row(record: MonthlyBizIncome, row: Dict) -> MonthlyBizIncomeRow:
    def _to_int0(v) -> int:
        if v in (None, ""): return 0
        try: return int(float(str(v).replace(",","")))
        except Exception: return 0
    name = str(row.get("name") or "").strip()
    pid_raw = str(row.get("pid") or "").strip()
    # Encrypt if possible, otherwise mask (same policy as payroll)
    enc = encrypt_ssn(pid_raw)
    pid_store = enc if enc.startswith("enc:") else mask_ssn(pid_raw)
    amount = _to_int0(row.get("amount"))
    try:
        rate = int(str(row.get("rate") or 3).split(".")[0])
    except Exception:
        rate = 3
    # 10원 단위 절사 적용
    def _floor10(x: float) -> int:
        try:
            v = int(x)
        except Exception:
            v = 0
        return (v // 10) * 10
    tax = _floor10(amount * (rate / 100))
    local = _floor10(tax * 0.1)
    total = tax + local
    net = amount - total
    return MonthlyBizIncomeRow(
        bizincome_id=record.id,
        company_id=record.company_id,
        name=name,
        pid=pid_store,
        resident_type=str(row.get("resident_type") or ""),
        biz_type=str(row.get("biz_type") or ""),
        amount=amount,
        rate=rate,
        tax=tax,
        local_tax=local,
        total_tax=total,
        net_amount=net,
        year=record.year,
        month=record.month,
        is_closed=bool(getattr(record, "is_closed", False)),
    )
