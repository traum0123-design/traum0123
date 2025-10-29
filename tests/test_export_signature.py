from __future__ import annotations

import time

from fastapi.testclient import TestClient


def setup_env(monkeypatch):
    from core.db import init_database, get_sessionmaker
    from sqlalchemy.orm import Session
    from core.models import Company, MonthlyPayroll
    import datetime as dt
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    monkeypatch.setenv("PAYROLL_AUTO_APPLY_DDL", "1")
    monkeypatch.setenv("SECRET_KEY", "secret")
    init_database(auto_apply_ddl=True)
    SessionLocal = get_sessionmaker()
    with SessionLocal() as db:  # type: Session
        c = Company(name="Demo", slug="acme", access_hash="x", token_key="k", created_at=dt.datetime.now(dt.UTC))
        db.add(c); db.commit(); db.refresh(c)
        mp = MonthlyPayroll(company_id=c.id, year=2025, month=10, rows_json="[]")
        db.add(mp); db.commit()
        return SessionLocal, c.id, c.slug


def make_token(company_id: int, slug: str):
    from core.auth import make_company_token
    from core.settings import get_settings
    return make_company_token(get_settings().secret_key, company_id, slug, key="k", roles=["viewer"])


def test_export_requires_signature_when_enabled(monkeypatch):
    SessionLocal, cid, slug = setup_env(monkeypatch)
    from app.main import create_app
    app = create_app()
    client = TestClient(app)
    tok = make_token(cid, slug)

    # Enable signature
    secret = "supersecret"
    monkeypatch.setenv("EXPORT_HMAC_SECRET", secret)

    # Missing signature
    r = client.get(f"/api/portal/{slug}/export/2025/10", headers={"X-API-Token": tok})
    assert r.status_code == 403

    # Valid signature
    import hmac, hashlib
    path = f"/api/portal/{slug}/export/2025/10"
    exp = int(time.time()) + 60
    msg = f"{path}|{exp}|{cid}".encode()
    sig = hmac.new(secret.encode(), msg, hashlib.sha256).hexdigest()
    r2 = client.get(f"/api/portal/{slug}/export/2025/10?exp={exp}&sig={sig}", headers={"X-API-Token": tok})
    assert r2.status_code == 200

