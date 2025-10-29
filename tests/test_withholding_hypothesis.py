from __future__ import annotations

import pytest

hypothesis = pytest.importorskip("hypothesis")
st = pytest.importorskip("hypothesis.strategies")

from sqlalchemy.orm import Session


@hypothesis.given(
    wages=st.lists(st.integers(min_value=1000, max_value=10_000_000), min_size=3, max_size=8, unique=True).map(lambda xs: sorted(xs)),
    taxes=st.lists(st.integers(min_value=0, max_value=1_000_000), min_size=3, max_size=8).map(lambda xs: sorted(xs)),
)
def test_withholding_monotonic_property(wages, taxes, monkeypatch):
    # Align sizes
    n = min(len(wages), len(taxes))
    wages = wages[:n]
    taxes = taxes[:n]
    from core.db import init_database, get_sessionmaker
    from core.models import WithholdingCell
    from core.services.payroll import compute_withholding_tax
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    init_database(auto_apply_ddl=True)
    SessionLocal = get_sessionmaker()
    with SessionLocal() as db:  # type: Session
        db.add_all([WithholdingCell(year=2025, dependents=1, wage=w, tax=t) for w, t in zip(wages, taxes)])
        db.commit()
        # Queries across a grid should be non-decreasing in wage
        grid = list(range(wages[0]-1, wages[-1]+2, max(1, (wages[-1]-wages[0])//(n-1) or 1)))
        vals = [compute_withholding_tax(db, 2025, 1, w) for w in grid]
        assert vals == sorted(vals)

