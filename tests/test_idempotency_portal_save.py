from __future__ import annotations

import os

from fastapi.testclient import TestClient


def test_portal_save_idempotency(monkeypatch):
    from app.main import create_app
    from core.db import init_database, get_sessionmaker
    from sqlalchemy.orm import Session
    from core.models import Company, MonthlyPayroll
    import datetime as dt
    import secrets

    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    monkeypatch.setenv("PAYROLL_AUTO_APPLY_DDL", "1")
    monkeypatch.setenv("SECRET_KEY", "secret")

    init_database(auto_apply_ddl=True)
    SessionLocal = get_sessionmaker()
    app = create_app()
    client = TestClient(app)

    slug = f"demo_{secrets.token_hex(3)}"
    with SessionLocal() as db:  # type: Session
        c = Company(name="X", slug=slug, access_hash="x", token_key="t", created_at=dt.datetime.now(dt.UTC))
        db.add(c); db.commit(); db.refresh(c)
        # token with manager role
        from core.services.auth import issue_company_token
        tok = issue_company_token(db, c, ensure_key=False, is_admin=False, roles=["payroll_manager"])

    rows = {"rows": [{"사원코드": "E01", "사원명": "홍길동", "기본급": 1000}]}
    headers = {"X-API-Token": tok, "Idempotency-Key": "idem-key-1", "Content-Type": "application/json"}
    r1 = client.post(f"/api/portal/{slug}/payroll/2025/10", headers=headers, json=rows)
    assert r1.status_code in (200, 201)
    r2 = client.post(f"/api/portal/{slug}/payroll/2025/10", headers=headers, json=rows)
    assert r2.status_code in (200, 201)
    # verify single record
    with SessionLocal() as db:
        cnt = db.query(MonthlyPayroll).filter(MonthlyPayroll.year == 2025, MonthlyPayroll.month == 10).count()
        assert cnt == 1

