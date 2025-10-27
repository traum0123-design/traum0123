from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from core.models import Company


def get_by_slug(session: Session, slug: str) -> Company | None:
    return session.query(Company).filter(Company.slug == slug).first()


def get_by_id(session: Session, company_id: int) -> Company | None:
    return session.get(Company, company_id)


def list_companies(session: Session) -> list[Company]:
    return (
        session.query(Company)
        .order_by(Company.created_at.desc())
        .all()
    )
