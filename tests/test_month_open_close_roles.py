from __future__ import annotations

from fastapi.testclient import TestClient


def setup_company(monkeypatch):
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
        c = Company(name="Demo", slug=slug, access_hash="x", token_key="kk", created_at=dt.datetime.now(dt.UTC))
        db.add(c); db.commit(); db.refresh(c)
        return SessionLocal, c.id, c.slug


def make_token(company_id: int, slug: str, roles: list[str]):
    from core.auth import make_company_token
    from core.settings import get_settings
    return make_company_token(get_settings().secret_key, company_id, slug, key="kk", roles=roles)


def test_close_open_requires_company_admin_or_admin(monkeypatch):
    SessionLocal, cid, slug = setup_company(monkeypatch)
    from app.main import create_app
    app = create_app()
    client = TestClient(app)
    viewer = make_token(cid, slug, ["viewer"])
    mgr = make_token(cid, slug, ["payroll_manager"])
    cadm = make_token(cid, slug, ["company_admin"])

    # viewer forbidden
    r = client.post(f"/api/portal/{slug}/payroll/2025/10/close", headers={"X-API-Token": viewer})
    assert r.status_code == 403
    # manager forbidden
    r = client.post(f"/api/portal/{slug}/payroll/2025/10/close", headers={"X-API-Token": mgr})
    assert r.status_code == 403
    # company_admin allowed
    r = client.post(f"/api/portal/{slug}/payroll/2025/10/close", headers={"X-API-Token": cadm})
    assert r.status_code in (200, 201)
    # reopen
    r = client.post(f"/api/portal/{slug}/payroll/2025/10/open", headers={"X-API-Token": cadm})
    assert r.status_code in (200, 201)

