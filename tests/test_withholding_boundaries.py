from __future__ import annotations

from sqlalchemy.orm import Session


def test_withholding_bracket_boundaries(monkeypatch):
    from core.db import init_database, get_sessionmaker
    from core.models import WithholdingCell
    from core.services.payroll import compute_withholding_tax
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    init_database(auto_apply_ddl=True)
    SessionLocal = get_sessionmaker()
    with SessionLocal() as db:  # type: Session
        db.add_all([
            WithholdingCell(year=2025, dependents=1, wage=1000000, tax=50000),
            WithholdingCell(year=2025, dependents=1, wage=2000000, tax=110000),
            WithholdingCell(year=2025, dependents=1, wage=3000000, tax=200000),
        ])
        db.commit()
        # Just below / at / above boundary
        assert compute_withholding_tax(db, 2025, 1, 1999999) == 50000
        assert compute_withholding_tax(db, 2025, 1, 2000000) == 110000
        assert compute_withholding_tax(db, 2025, 1, 2000001) == 110000

