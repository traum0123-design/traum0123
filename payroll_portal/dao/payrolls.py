from __future__ import annotations

from typing import List, Optional

from sqlalchemy.orm import Session

from payroll_shared.models import MonthlyPayroll, WithholdingCell


def list_for_year(session: Session, company_id: int, year: int) -> List[MonthlyPayroll]:
    return (
        session.query(MonthlyPayroll)
        .filter(MonthlyPayroll.company_id == company_id, MonthlyPayroll.year == year)
        .all()
    )


def get_by_month(session: Session, company_id: int, year: int, month: int) -> Optional[MonthlyPayroll]:
    return (
        session.query(MonthlyPayroll)
        .filter(
            MonthlyPayroll.company_id == company_id,
            MonthlyPayroll.year == year,
            MonthlyPayroll.month == month,
        )
        .first()
    )


def upsert(session: Session, payroll: MonthlyPayroll) -> MonthlyPayroll:
    session.add(payroll)
    session.flush()
    return payroll


def latest_withholding(
    session: Session,
    year: int,
    dependents: int,
    wage: int,
) -> Optional[WithholdingCell]:
    return (
        session.query(WithholdingCell)
        .filter(
            WithholdingCell.year == year,
            WithholdingCell.dependents == dependents,
            WithholdingCell.wage <= wage,
        )
        .order_by(WithholdingCell.wage.desc())
        .first()
    )

