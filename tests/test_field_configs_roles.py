from __future__ import annotations

from fastapi.testclient import TestClient


def setup_env(monkeypatch):
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
        c = Company(name="Demo", slug=slug, access_hash="x", token_key="tk2", created_at=dt.datetime.now(dt.UTC))
        db.add(c); db.commit(); db.refresh(c)
        return SessionLocal, c.id, c.slug


def make_token(company_id: int, slug: str, roles: list[str]):
    from core.auth import make_company_token
    from core.settings import get_settings
    return make_company_token(get_settings().secret_key, company_id, slug, key="tk2", roles=roles)


def test_exempt_config_roles(monkeypatch):
    SessionLocal, cid, slug = setup_env(monkeypatch)
    from app.main import create_app
    app = create_app()
    client = TestClient(app)
    viewer = make_token(cid, slug, ["viewer"])
    mgr = make_token(cid, slug, ["payroll_manager"])

    # viewer cannot save
    r = client.post(
        f"/api/portal/{slug}/fields/exempt-config",
        headers={"X-API-Token": viewer, "Content-Type": "application/json"},
        json={"exempt": {"식대": {"enabled": True, "limit": 200000}}},
    )
    assert r.status_code == 403

    # manager can save
    r2 = client.post(
        f"/api/portal/{slug}/fields/exempt-config",
        headers={"X-API-Token": mgr, "Content-Type": "application/json"},
        json={"exempt": {"식대": {"enabled": True, "limit": 200000}}},
    )
    assert r2.status_code in (200, 201)


def test_group_config_roles(monkeypatch):
    SessionLocal, cid, slug = setup_env(monkeypatch)
    from app.main import create_app
    app = create_app()
    client = TestClient(app)
    viewer = make_token(cid, slug, ["viewer"])
    mgr = make_token(cid, slug, ["payroll_manager"])

    payload = {"map": {"기본급": "earn"}, "alias": {"기본급": "Base"}}
    r = client.post(
        f"/api/portal/{slug}/fields/group-config",
        headers={"X-API-Token": viewer, "Content-Type": "application/json"},
        json=payload,
    )
    assert r.status_code == 403

    r2 = client.post(
        f"/api/portal/{slug}/fields/group-config",
        headers={"X-API-Token": mgr, "Content-Type": "application/json"},
        json=payload,
    )
    assert r2.status_code in (200, 201)

