from __future__ import annotations

from fastapi.testclient import TestClient


def setup_demo(monkeypatch):
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
    slug = f"demo_{secrets.token_hex(2)}"
    with SessionLocal() as db:  # type: Session
        c = Company(name="Demo", slug=slug, access_hash="x", token_key="key1", created_at=dt.datetime.now(dt.UTC))
        db.add(c); db.commit(); db.refresh(c)
        return SessionLocal, c.id, c.slug


def make_token(company_id: int, slug: str, roles: list[str]):
    from core.auth import make_company_token
    from core.settings import get_settings
    secret = get_settings().secret_key
    return make_company_token(secret, company_id, slug, key="key1", roles=roles)


def test_calc_config_get_allowed_for_viewer(monkeypatch):
    SessionLocal, cid, slug = setup_demo(monkeypatch)
    from app.main import create_app
    app = create_app()
    client = TestClient(app)
    token = make_token(cid, slug, ["viewer"])
    r = client.get(f"/api/portal/{slug}/fields/calc-config", headers={"X-API-Token": token})
    assert r.status_code == 200
    assert r.json().get("ok") in (True, None)


def test_calc_config_post_requires_manager_or_admin(monkeypatch):
    SessionLocal, cid, slug = setup_demo(monkeypatch)
    from app.main import create_app
    app = create_app()
    client = TestClient(app)
    viewer = make_token(cid, slug, ["viewer"])
    r = client.post(
        f"/api/portal/{slug}/fields/calc-config",
        headers={"X-API-Token": viewer, "Content-Type": "application/json"},
        json={"include": {"nhis": {"기본급": True}}},
    )
    assert r.status_code == 403
    mgr = make_token(cid, slug, ["payroll_manager"])
    r2 = client.post(
        f"/api/portal/{slug}/fields/calc-config",
        headers={"X-API-Token": mgr, "Content-Type": "application/json"},
        json={"include": {"nhis": {"기본급": True}}},
    )
    assert r2.status_code in (200, 201)

