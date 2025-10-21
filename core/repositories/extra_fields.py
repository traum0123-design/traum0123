from __future__ import annotations

from typing import List, Optional

from sqlalchemy.orm import Session

from core.models import ExtraField


def list_for_company(session: Session, company_id: int) -> List[ExtraField]:
    return (
        session.query(ExtraField)
        .filter(ExtraField.company_id == company_id)
        .order_by(ExtraField.position.asc(), ExtraField.id.asc())
        .all()
    )


def find_by_label(session: Session, company_id: int, label: str) -> Optional[ExtraField]:
    return (
        session.query(ExtraField)
        .filter(ExtraField.company_id == company_id, ExtraField.label == label)
        .first()
    )


def find_by_name(session: Session, company_id: int, name: str) -> Optional[ExtraField]:
    return (
        session.query(ExtraField)
        .filter(ExtraField.company_id == company_id, ExtraField.name == name)
        .first()
    )


def add(session: Session, field: ExtraField) -> ExtraField:
    session.add(field)
    session.flush()
    return field
