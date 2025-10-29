from __future__ import annotations

from fastapi.testclient import TestClient


def test_policy_history_records(monkeypatch):
    from app.main import create_app
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

    app = create_app()
    client = TestClient(app)
    # Admin token via API
    r = client.post("/api/admin/login", data={"password": ""})
    # login requires configured admin password; fallback to direct header for testing
    from core.auth import make_admin_token
    from core.settings import get_settings
    admin_tok = make_admin_token(get_settings().secret_key)

    # Set + update policy
    p1 = {"local_tax": {"round_to": 10}}
    p2 = {"local_tax": {"round_to": 1}}
    r1 = client.post("/api/admin/policy?year=2025", headers={"X-Admin-Token": admin_tok, "Content-Type": "application/json"}, json=p1)
    assert r1.status_code in (200, 201)
    r2 = client.post("/api/admin/policy?year=2025", headers={"X-Admin-Token": admin_tok, "Content-Type": "application/json"}, json=p2)
    assert r2.status_code in (200, 201)
    # Fetch history
    rh = client.get("/api/admin/policy/history?year=2025", headers={"X-Admin-Token": admin_tok})
    assert rh.status_code == 200
    data = rh.json()
    assert data.get("ok") in (True, None)
    assert len(data.get("items") or []) >= 2

