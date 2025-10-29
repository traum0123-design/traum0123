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
        return SessionLocal, c.id, c.slug


def make_token(company_id: int, slug: str):
    from core.auth import make_company_token
    from core.settings import get_settings
    return make_company_token(get_settings().secret_key, company_id, slug, key="k", roles=["payroll_manager"])


def test_cookie_write_invalid_origin_blocked(monkeypatch):
    SessionLocal, cid, slug = setup_env(monkeypatch)
    from app.main import create_app
    app = create_app()
    client = TestClient(app)
    tok = make_token(cid, slug)
    # Set cookie auth and CSRF cookie/header, but Origin is invalid → should block
    headers = {"Origin": "http://evil.local", "X-CSRF-Token": "token123", "Content-Type": "application/json"}
    cookies = {"portal_token": tok, "portal_csrf": "token123"}
    r = client.post(f"/api/portal/{slug}/ui-prefs", headers=headers, cookies=cookies, json={"values": {"x": 1}})
    assert r.status_code == 403

