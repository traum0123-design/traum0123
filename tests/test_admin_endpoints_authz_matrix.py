from __future__ import annotations

from fastapi.testclient import TestClient


def setup_company(monkeypatch):
    from core.db import init_database, get_sessionmaker
    from sqlalchemy.orm import Session
    from core.models import Company
    import datetime as dt
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    monkeypatch.setenv("PAYROLL_AUTO_APPLY_DDL", "1")
    monkeypatch.setenv("SECRET_KEY", "secret")
    init_database(auto_apply_ddl=True)
    SessionLocal = get_sessionmaker()
    with SessionLocal() as db:  # type: Session
        c = Company(name="Demo", slug="acme", access_hash="x", token_key="k", created_at=dt.datetime.now(dt.UTC))
        db.add(c); db.commit(); db.refresh(c)
        return SessionLocal, c.id


def admin_token():
    from core.auth import make_admin_token
    from core.settings import get_settings
    return make_admin_token(get_settings().secret_key)


def test_admin_endpoints_require_admin(monkeypatch):
    SessionLocal, company_id = setup_company(monkeypatch)
    from app.main import create_app
    app = create_app()
    client = TestClient(app)

    # rotate-token-key requires admin
    r = client.post(f"/api/admin/company/{company_id}/rotate-token-key")
    assert r.status_code == 403
    r2 = client.post(f"/api/admin/company/{company_id}/rotate-token-key", headers={"X-Admin-Token": admin_token()})
    assert r2.status_code in (200, 201)

    # impersonate-token requires admin
    r3 = client.get(f"/api/admin/company/{company_id}/impersonate-token")
    assert r3.status_code == 403
    r4 = client.get(f"/api/admin/company/{company_id}/impersonate-token", headers={"X-Admin-Token": admin_token()})
    assert r4.status_code == 200

    # policy set/history require admin
    r5 = client.post("/api/admin/policy?year=2025", json={"local_tax": {"round_to": 10}})
    assert r5.status_code == 403
    r6 = client.post("/api/admin/policy?year=2025", json={"local_tax": {"round_to": 10}}, headers={"X-Admin-Token": admin_token()})
    assert r6.status_code in (200, 201)
    r7 = client.get("/api/admin/policy/history?year=2025")
    assert r7.status_code == 403
    r8 = client.get("/api/admin/policy/history?year=2025", headers={"X-Admin-Token": admin_token()})
    assert r8.status_code == 200

