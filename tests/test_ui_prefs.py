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
    return make_company_token(get_settings().secret_key, company_id, slug, key="k", roles=["viewer"])


def test_ui_prefs_set_and_get(monkeypatch):
    SessionLocal, cid, slug = setup_env(monkeypatch)
    from app.main import create_app
    app = create_app()
    client = TestClient(app)
    tok = make_token(cid, slug)

    # Set prefs (as viewer)
    payload = {"values": {"table.columnWidths": {"기본급": 180}}}
    r = client.post(f"/api/portal/{slug}/ui-prefs", headers={"X-API-Token": tok, "Content-Type": "application/json"}, json=payload)
    assert r.status_code in (200, 201)

    # Get prefs
    r2 = client.get(f"/api/portal/{slug}/ui-prefs?keys=table.columnWidths", headers={"X-API-Token": tok})
    assert r2.status_code == 200
    data = r2.json()
    assert (data.get("values") or {}).get("table.columnWidths") == {"기본급": 180}

