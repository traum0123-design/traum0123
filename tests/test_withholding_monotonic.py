from __future__ import annotations

from sqlalchemy.orm import Session
from fastapi.testclient import TestClient


def test_withholding_monotonic(monkeypatch):
    from core.db import init_database, get_sessionmaker
    from core.models import WithholdingCell
    from payroll_api.main import create_app
    from sqlalchemy import select

    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    init_database(auto_apply_ddl=True)
    SessionLocal = get_sessionmaker()
    with SessionLocal() as db:  # type: Session
        # seed ascending wages and non-decreasing taxes
        rows = [
            WithholdingCell(year=2025, dependents=1, wage=1_000_000, tax=50_000),
            WithholdingCell(year=2025, dependents=1, wage=2_000_000, tax=110_000),
            WithholdingCell(year=2025, dependents=1, wage=3_000_000, tax=200_000),
        ]
        db.add_all(rows); db.commit()

        # verify compute_withholding_tax is monotonic non-decreasing in wage intervals
        from core.services.payroll import compute_withholding_tax
        vals = [compute_withholding_tax(db, 2025, 1, w) for w in [900_000, 1_000_000, 1_500_000, 2_000_000, 2_500_000, 3_000_000, 5_000_000]]
        assert vals == sorted(vals), f"taxes should be non-decreasing: {vals}"

