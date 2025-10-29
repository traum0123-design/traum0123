from __future__ import annotations

from fastapi.testclient import TestClient


def test_idempotency_conflict(monkeypatch):
    from app.main import create_app
    from core.db import init_database, get_sessionmaker
    from sqlalchemy.orm import Session
    from core.models import Company
    import datetime as dt
    import secrets

    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    monkeypatch.setenv("PAYROLL_AUTO_APPLY_DDL", "1")
    monkeypatch.setenv("SECRET_KEY", "secret")

    init_database(auto_apply_ddl=True)
    SessionLocal = get_sessionmaker()
    slug = f"demo_{secrets.token_hex(3)}"
    with SessionLocal() as db:  # type: Session
        c = Company(name="X", slug=slug, access_hash="x", token_key="t", created_at=dt.datetime.now(dt.UTC))
        db.add(c); db.commit(); db.refresh(c)
        from core.services.auth import issue_company_token
        tok = issue_company_token(db, c, ensure_key=False, is_admin=False, roles=["payroll_manager"])

    app = create_app()
    client = TestClient(app)
    headers = {"X-API-Token": tok, "Idempotency-Key": "same-key", "Content-Type": "application/json"}
    body1 = {"rows": [{"사원코드": "E01", "기본급": 1000}]}
    body2 = {"rows": [{"사원코드": "E01", "기본급": 2000}]}
    r1 = client.post(f"/api/portal/{slug}/payroll/2025/10", headers=headers, json=body1)
    assert r1.status_code in (200, 201)
    r2 = client.post(f"/api/portal/{slug}/payroll/2025/10", headers=headers, json=body2)
    # Same key but different body → 409 conflict expected
    assert r2.status_code == 409

