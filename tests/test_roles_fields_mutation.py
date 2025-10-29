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
        c = Company(name="Demo", slug=slug, access_hash="x", token_key="tk1", created_at=dt.datetime.now(dt.UTC))
        db.add(c); db.commit(); db.refresh(c)
        return SessionLocal, c.id, c.slug


def make_token(company_id: int, slug: str, roles: list[str]):
    from core.auth import make_company_token
    from core.settings import get_settings
    return make_company_token(get_settings().secret_key, company_id, slug, key="tk1", roles=roles)


def test_fields_add_delete_roles(monkeypatch):
    SessionLocal, cid, slug = setup_env(monkeypatch)
    from app.main import create_app
    app = create_app()
    client = TestClient(app)
    viewer = make_token(cid, slug, ["viewer"])
    mgr = make_token(cid, slug, ["payroll_manager"])

    # viewer cannot add
    r = client.post(
        f"/api/portal/{slug}/fields/add",
        headers={"X-API-Token": viewer, "Content-Type": "application/json"},
        json={"label": "식대", "typ": "number"},
    )
    assert r.status_code == 403

    # manager can add
    r2 = client.post(
        f"/api/portal/{slug}/fields/add",
        headers={"X-API-Token": mgr, "Content-Type": "application/json"},
        json={"label": "식대", "typ": "number"},
    )
    assert r2.status_code in (200, 201)
    name = r2.json().get("field", {}).get("name") or "식대"

    # viewer cannot delete
    r3 = client.post(
        f"/api/portal/{slug}/fields/delete",
        headers={"X-API-Token": viewer, "Content-Type": "application/json"},
        json={"name": name},
    )
    assert r3.status_code == 403

    # manager can delete
    r4 = client.post(
        f"/api/portal/{slug}/fields/delete",
        headers={"X-API-Token": mgr, "Content-Type": "application/json"},
        json={"name": name},
    )
    assert r4.status_code in (200, 201)

