from __future__ import annotations

import datetime as dt
from sqlalchemy.orm import Session

from core.db import session_scope, init_database
from core.models import Company
from core.services import companies as company_service


def main() -> None:
    init_database(auto_apply_ddl=True)
    with session_scope() as session:
        _seed_company(session)


def _seed_company(session: Session) -> None:
    slug = "demo-co"
    existing = session.query(Company).filter(Company.slug == slug).first()
    if existing:
        print(f"Company already exists: {existing.slug} (id={existing.id})")
        return
    company, code = company_service.create_company(session, name="데모회사", slug=slug)
    print(f"Created company: {company.slug} (id={company.id})")
    print(f"Portal access code: {code}")
    print(f"Portal login URL: /portal/{company.slug}/login")


if __name__ == "__main__":
    main()

