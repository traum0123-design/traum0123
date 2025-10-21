from __future__ import annotations

from typing import List, Optional

from sqlalchemy.orm import Session

from payroll_shared.models import Company


def get_by_slug(session: Session, slug: str) -> Optional[Company]:
    return session.query(Company).filter(Company.slug == slug).first()


def get_by_id(session: Session, company_id: int) -> Optional[Company]:
    return session.get(Company, company_id)


def list_companies(session: Session) -> List[Company]:
    return (
        session.query(Company)
        .order_by(Company.created_at.desc())
        .all()
    )

