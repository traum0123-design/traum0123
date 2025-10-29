from __future__ import annotations

from fastapi.testclient import TestClient


def setup_env(monkeypatch):
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


def test_admin_required_on_admin_routes(monkeypatch):
    SessionLocal, company_id = setup_env(monkeypatch)
    from app.main import create_app
    app = create_app()
    client = TestClient(app)
    # Without admin token → 403
    r = client.post(f"/api/admin/company/{company_id}/reset-code")
    assert r.status_code == 403
    # With admin token → 200
    from core.auth import make_admin_token
    from core.settings import get_settings
    adm = make_admin_token(get_settings().secret_key)
    r2 = client.post(f"/api/admin/company/{company_id}/reset-code", headers={"X-Admin-Token": adm})
    assert r2.status_code in (200, 201)

