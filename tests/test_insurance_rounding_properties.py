from __future__ import annotations

import pytest
from decimal import Decimal

hypothesis = pytest.importorskip("hypothesis")
st = pytest.importorskip("hypothesis.strategies")


@hypothesis.given(
    base=st.integers(min_value=0, max_value=10_000_000),
    rate=st.decimals(min_value=0, max_value=0.2, places=4),
    step=st.integers(min_value=1, max_value=1000),
)
def test_health_insurance_rounding_monotonic(monkeypatch, base, rate, step):
    # Configure env for NHIS rounding step/mode
    monkeypatch.setenv("INS_NHIS_RATE", str(rate))
    monkeypatch.setenv("INS_NHIS_ROUND_TO", str(step))
    monkeypatch.setenv("INS_NHIS_ROUNDING", "round")

    # Build a simple company and call compute_deductions
    from core.db import init_database, get_sessionmaker
    from core.models import Company
    from sqlalchemy.orm import Session
    from core.services.calculation import compute_deductions
    import datetime as dt

    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    init_database(auto_apply_ddl=True)
    SessionLocal = get_sessionmaker()
    with SessionLocal() as db:  # type: Session
        c = Company(name="Demo", slug="acme", access_hash="x", token_key="k", created_at=dt.datetime.now(dt.UTC))
        db.add(c); db.commit(); db.refresh(c)
        # Two rows with base and base+step
        row1 = {"기본급": int(base)}
        row2 = {"기본급": int(base + step)}
        a1, _ = compute_deductions(db, c, row1, 2025)
        a2, _ = compute_deductions(db, c, row2, 2025)
        assert a1['health_insurance'] <= a2['health_insurance']

