from __future__ import annotations

import secrets
from typing import Optional

from sqlalchemy.orm import Session
from werkzeug.security import check_password_hash, generate_password_hash

from core.models import Company
from core.repositories import companies as companies_repo
from core.settings import get_settings


def verify_admin_password(password: str) -> bool:
    candidate = (password or "").strip()
    expected = (get_settings().admin_password or "").strip()
    if not expected or not candidate:
        return False
    try:
        return check_password_hash(expected, candidate)
    except ValueError:
        return secrets.compare_digest(candidate, expected)


def validate_company_access(session: Session, company: Company, access_code: str) -> bool:
    return check_password_hash(company.access_hash, access_code.strip())


def create_company(session: Session, name: str, slug: str) -> tuple[Company, str]:
    slug = slug.strip().lower()
    company = Company(name=name.strip(), slug=slug, access_hash="")
    session.add(company)
    session.flush()
    code = rotate_company_access(session, company)
    return company, code


def rotate_company_access(session: Session, company: Company) -> str:
    code = secrets.token_hex(4)
    company.access_hash = generate_password_hash(code)
    session.commit()
    return code


def ensure_token_key(session: Session, company: Company) -> None:
    if company.token_key and company.token_key.strip():
        return
    company.token_key = secrets.token_hex(16)
    session.commit()

def rotate_company_token_key(session: Session, company: Company) -> str:
    """Rotate company's token key to immediately revoke existing tokens.

    Returns the new key (not exposed to clients; only for internal auditing/tests).
    """
    company.token_key = secrets.token_hex(16)
    session.commit()
    return company.token_key


def find_company_by_slug(session: Session, slug: str) -> Company | None:
    return companies_repo.get_by_slug(session, slug)


def find_company_by_id(session: Session, company_id: int) -> Company | None:
    return companies_repo.get_by_id(session, company_id)
