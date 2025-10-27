from __future__ import annotations

import datetime as dt

from sqlalchemy.orm import Session

from core.models import Company, WithholdingCell
from core.services.auth import issue_company_token
from payroll_api import main as api_main


def test_compute_withholding_tax_returns_exact_match(session: Session):
    session.add(WithholdingCell(year=2024, dependents=1, wage=3000000, tax=123000))
    session.add(WithholdingCell(year=2024, dependents=1, wage=2800000, tax=110000))
    session.commit()

    tax = api_main.compute_withholding_tax(session, year=2024, dependents=1, wage=2999999)
    assert tax == 110000

    tax_high = api_main.compute_withholding_tax(session, year=2024, dependents=1, wage=3000000)
    assert tax_high == 123000


def test_issue_and_require_company_token(session: Session):
    company = Company(
        name="테스트회사",
        slug="test-co",
        access_hash="dummy",
        token_key="",
        created_at=dt.datetime.now(dt.UTC),
    )
    session.add(company)
    session.commit()

    token = issue_company_token(session, company)

    resolved = api_main.require_company(
        slug="test-co",
        db=session,
        authorization=f"Bearer {token}",
    )
    assert resolved.id == company.id
