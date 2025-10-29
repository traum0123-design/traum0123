from __future__ import annotations

import json

from fastapi.testclient import TestClient


def _seed_company(session) -> tuple[int, str, str]:
    import datetime as dt
    from core.models import Company
    from core.services.auth import issue_company_token

    import secrets
    slug = f"idem-{secrets.token_hex(3)}"
    c = Company(name="아이디", slug=slug, access_hash="x", token_key="", created_at=dt.datetime.now(dt.UTC))
    session.add(c)
    session.commit()
    session.refresh(c)
    tok = issue_company_token(session, c)
    return c.id, c.slug, tok


def test_idempotency_save_payroll_same_key_same_payload(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    from core.db import init_database, get_sessionmaker
    from app.main import create_app
    from core.models import MonthlyPayroll

    init_database(auto_apply_ddl=True)
    SessionLocal = get_sessionmaker()
    with SessionLocal() as session:
        _, slug, token = _seed_company(session)

    app = create_app()
    client = TestClient(app)

    rows = [{"사원코드": "E1", "사원명": "A", "기본급": 1000}]
    headers = {"Authorization": f"Bearer {token}", "Idempotency-Key": "key-1"}
    r1 = client.post(f"/api/portal/{slug}/payroll/2024/5", json={"rows": rows}, headers=headers)
    assert r1.status_code == 200
    r2 = client.post(f"/api/portal/{slug}/payroll/2024/5", json={"rows": rows}, headers=headers)
    assert r2.status_code == 200

    # Ensure only one monthly record exists
    with SessionLocal() as session:
        from core.models import Company
        comp = session.query(Company).filter(Company.slug == slug).first()
        assert comp is not None
        cnt = session.query(MonthlyPayroll).filter(MonthlyPayroll.company_id == comp.id, MonthlyPayroll.year == 2024, MonthlyPayroll.month == 5).count()
        assert cnt == 1


def test_idempotency_conflict_on_different_payload(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    from core.db import init_database, get_sessionmaker
    from app.main import create_app

    init_database(auto_apply_ddl=True)
    SessionLocal = get_sessionmaker()
    with SessionLocal() as session:
        _, slug, token = _seed_company(session)

    app = create_app()
    client = TestClient(app)
    headers = {"Authorization": f"Bearer {token}", "Idempotency-Key": "key-2"}
    r1 = client.post(f"/api/portal/{slug}/payroll/2024/6", json={"rows": [{"사원명": "A"}]}, headers=headers)
    assert r1.status_code == 200
    # Different payload with same key should raise 409
    r2 = client.post(f"/api/portal/{slug}/payroll/2024/6", json={"rows": [{"사원명": "B"}]}, headers=headers)
    assert r2.status_code == 409


def test_problem_json_negotiation_on_error(monkeypatch):
    # Missing token should yield 403 with problem+json when requested
    from app.main import create_app

    app = create_app()
    client = TestClient(app)
    r = client.get(
        "/api/portal/nope/payroll/2024/5",
        headers={"Accept": "application/problem+json"},
    )
    assert r.status_code in (403, 404)
    assert r.headers.get("content-type", "").lower().startswith("application/problem+json")
    body = r.json()
    assert "status" in body and body.get("type")
