from __future__ import annotations

from sqlalchemy.orm import Session


def test_withholding_compute_helper(session: Session):
    # Seed withholding table
    from core.models import WithholdingCell, Company
    from payroll_api import main as api_main

    session.add(WithholdingCell(year=2024, dependents=1, wage=2_800_000, tax=110_000))
    session.add(WithholdingCell(year=2024, dependents=1, wage=3_000_000, tax=123_000))
    session.commit()

    # Compute exact match and nearest lower
    assert api_main.compute_withholding_tax(session, year=2024, dependents=1, wage=2_999_999) == 110_000
    assert api_main.compute_withholding_tax(session, year=2024, dependents=1, wage=3_000_000) == 123_000
